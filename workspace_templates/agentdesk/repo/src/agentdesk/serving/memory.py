"""VRAM accounting for the self-hosted model.

**What this is, and what it is not.**

There is no accelerator in this repository and no ``torch`` dependency. What runs here is
the *control plane* -- the arithmetic a serving stack does before it admits a request, and
the policy it applies when the answer is "not enough memory". That arithmetic is exact
integer arithmetic and is worth getting right for its own sake: nearly every production OOM in
a serving stack is a planning error, not an allocator error. The GPU did what it was told;
it was told wrong.

So: this module models where the bytes go. It does not model CUDA, kernels, or anything
you would need a card to observe.

**Where the bytes go.** Three claims on the budget, in descending order of size and
ascending order of how often people forget them:

1. **Weights.** ``params * dtype_bytes``. Fixed for the life of the process.
2. **KV cache.** Grows with every token, for every concurrent request. This is the one
   that moves, and therefore the one admission control exists to bound.
3. **Activations and workspace.** Transient per forward pass, scaling with batch size.
   Small next to the other two and routinely rounded to zero, which is how a stack ends up
   OOMing at exactly the batch size the planner said would fit.

**The KV formula, with the part people drop.**

    kv_per_token = 2 * layers * kv_heads * head_dim * dtype_bytes
                   ^
                   K and V are two separate tensors

That leading 2 is the single most commonly dropped term in this calculation, and dropping
it does not fail loudly -- it makes the planner believe it has twice the headroom it has,
so the stack runs beautifully until load doubles.

**Grouped-query attention.** ``kv_heads`` is the number of *key/value* heads, which under
GQA is smaller than the number of attention heads -- that is the whole point of GQA, and
the saving lands entirely in this cache. Using the attention head count here inflates the
estimate rather than deflating it, so it is the safe direction to be wrong in, which is
precisely why it survives review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Dtype = Literal["fp32", "fp16", "bf16", "fp8"]

#: Bytes per element. ``bf16`` is two bytes like ``fp16`` -- it trades mantissa bits for
#: exponent range, not size -- and the pair is a standing trap for anyone who assumes
#: "b" means "bigger".
DTYPE_BYTES: Final[dict[str, int]] = {
    "fp32": 4,
    "fp16": 2,
    "bf16": 2,
    "fp8": 1,
}

#: K and V. Written as a named constant so that dropping it is a visible deletion in a
#: diff rather than an invisible edit to a number.
KV_TENSORS_PER_LAYER: Final[int] = 2


class CapacityError(RuntimeError):
    """Raised when a plan does not fit in the budget it was given."""


@dataclass(frozen=True)
class ModelSpec:
    """The shape of a served model.

    Attributes:
        name: Identifier, for error messages.
        params: Parameter count.
        layers: Transformer blocks. The KV cache is per layer.
        kv_heads: Key/value heads. Under GQA this is below the attention head count.
        head_dim: Width of one head.
        weight_dtype: Dtype the weights are stored in.
        kv_dtype: Dtype the cache is stored in. Frequently differs from the weight dtype
            -- an fp8 cache against bf16 weights is a normal production configuration,
            and assuming one dtype for both is a 2x error in whichever direction.
        max_context: Longest sequence the model accepts.
    """

    name: str
    params: int
    layers: int
    kv_heads: int
    head_dim: int
    weight_dtype: Dtype = "bf16"
    kv_dtype: Dtype = "fp16"
    max_context: int = 8192

    def __str__(self) -> str:
        return f"{self.name} ({self.params / 1e9:.1f}B, {self.layers}L)"


def dtype_bytes(dtype: str) -> int:
    """Return bytes per element for a dtype.

    Raises:
        KeyError: For an unknown dtype. Deliberately not defaulted to 2 -- a silent
            default here is a silent halving or doubling of the entire budget.
    """
    return DTYPE_BYTES[dtype]


def weight_bytes(spec: ModelSpec) -> int:
    """Return bytes occupied by the weights."""
    return spec.params * dtype_bytes(spec.weight_dtype)


def kv_bytes_per_token(spec: ModelSpec) -> int:
    """Return KV cache bytes consumed by **one** token of **one** sequence."""
    return (
        KV_TENSORS_PER_LAYER
        * spec.layers
        * spec.kv_heads
        * spec.head_dim
        * dtype_bytes(spec.kv_dtype)
    )


def kv_bytes_for_request(spec: ModelSpec, *, prompt_tokens: int, max_new_tokens: int) -> int:
    """Return the KV cache a request will occupy **at its peak**.

    The peak is at the last generated token, not the first -- the cache holds the prompt
    *and* everything generated so far. Planning on the prompt alone is how a request is
    admitted happily and then OOMs two hundred tokens into its answer, by which point the
    user has been streamed half a reply.

    Args:
        spec: The served model.
        prompt_tokens: Tokens in the prompt.
        max_new_tokens: Most tokens the request may generate.

    Returns:
        Peak bytes for this request.

    Raises:
        ValueError: If the request cannot fit the model's context window at all.
    """
    total_tokens = prompt_tokens + max_new_tokens
    if total_tokens > spec.max_context:
        raise ValueError(
            f"{total_tokens} tokens exceeds {spec.name}'s context of {spec.max_context}"
        )
    return kv_bytes_per_token(spec) * total_tokens


def activation_bytes(spec: ModelSpec, *, batch_size: int) -> int:
    """Return transient activation and workspace bytes for a forward pass.

    A deliberately crude linear model, and crude is the right call: the true figure
    depends on kernel choices this layer cannot see. What matters is that it is **not
    zero**, because treating it as zero is what lets a planner fill the card exactly and
    then fall over on the first forward pass.
    """
    per_sequence = 2 * spec.layers * spec.kv_heads * spec.head_dim * dtype_bytes(spec.kv_dtype)
    return per_sequence * batch_size


@dataclass(frozen=True)
class Budget:
    """How a VRAM budget divides up.

    Attributes:
        total: The card's usable memory.
        weights: Taken by the weights.
        reserved: Held back for activations, workspace and fragmentation.
        kv_available: What is left for the KV cache. The number admission control spends.
    """

    total: int
    weights: int
    reserved: int
    kv_available: int

    @property
    def utilization(self) -> float:
        """Fraction of the card committed before any request is admitted."""
        return (self.weights + self.reserved) / self.total


def plan_budget(spec: ModelSpec, *, vram_bytes: int, max_batch: int = 32) -> Budget:
    """Divide a card between weights, reserve and KV cache.

    Args:
        spec: The served model.
        vram_bytes: Usable memory on the card.
        max_batch: Largest batch the scheduler will ever run, which sets the reserve.

    Returns:
        The resulting :class:`Budget`.

    Raises:
        CapacityError: If the weights and reserve alone do not fit, which means this model
            cannot be served on this card at any batch size.
    """
    weights = weight_bytes(spec)
    reserved = activation_bytes(spec, batch_size=max_batch)
    kv_available = vram_bytes - weights - reserved
    if kv_available <= 0:
        raise CapacityError(
            f"{spec} needs {weights + reserved} bytes for weights and reserve, "
            f"which does not fit in {vram_bytes}"
        )
    return Budget(
        total=vram_bytes, weights=weights, reserved=reserved, kv_available=kv_available
    )


def max_concurrent_requests(
    spec: ModelSpec, *, budget: Budget, prompt_tokens: int, max_new_tokens: int
) -> int:
    """Return how many identical requests fit in the KV budget at once.

    Uses each request's **peak**, not its starting size. A figure computed from prompt
    length alone is an admission limit that is correct for about one second.
    """
    per_request = kv_bytes_for_request(
        spec, prompt_tokens=prompt_tokens, max_new_tokens=max_new_tokens
    )
    return budget.kv_available // per_request
