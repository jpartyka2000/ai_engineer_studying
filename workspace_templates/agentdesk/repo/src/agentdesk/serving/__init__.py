"""The control plane for the self-hosted model: VRAM arithmetic, paging, admission.

**No accelerator is involved and none is required.** This package models where the bytes
go and who is allowed to spend them -- the planning layer, where production OOMs are
actually caused. It does not model CUDA, kernels or inference. :mod:`agentdesk.serving.memory`
says so at length and is worth reading before changing any number in here.
"""

from agentdesk.serving.blocks import BLOCK_TOKENS, BlockAllocator, OutOfBlocks, blocks_needed
from agentdesk.serving.memory import (
    DTYPE_BYTES,
    KV_TENSORS_PER_LAYER,
    Budget,
    CapacityError,
    ModelSpec,
    kv_bytes_for_request,
    kv_bytes_per_token,
    plan_budget,
    weight_bytes,
)
from agentdesk.serving.scheduler import Admission, Request, Scheduler, Verdict

__all__ = [
    "BLOCK_TOKENS",
    "DTYPE_BYTES",
    "KV_TENSORS_PER_LAYER",
    "Admission",
    "BlockAllocator",
    "Budget",
    "CapacityError",
    "ModelSpec",
    "OutOfBlocks",
    "Request",
    "Scheduler",
    "Verdict",
    "blocks_needed",
    "kv_bytes_for_request",
    "kv_bytes_per_token",
    "plan_budget",
    "weight_bytes",
]

#: The model this desk serves. A 8B-class model with grouped-query attention: 32 layers,
#: 8 KV heads against 32 attention heads, which is a 4x saving on the cache and the reason
#: it fits on one commodity card at a useful batch size.
DESK_8B = ModelSpec(
    name="desk-8b-instruct",
    params=8_030_000_000,
    layers=32,
    kv_heads=8,
    head_dim=128,
    weight_dtype="bf16",
    kv_dtype="fp16",
    max_context=8192,
)
