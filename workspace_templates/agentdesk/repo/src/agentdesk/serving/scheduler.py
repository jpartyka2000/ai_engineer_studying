"""Admission control and the decode loop.

**Two separate questions, deliberately answered by two separate mechanisms.**

*May this request start?* is answered by **reservation**: before a request is admitted,
the scheduler sets aside enough blocks for its **peak** -- prompt plus every token it is
permitted to generate. Reservations are bookkeeping, not memory; nothing is written.

*Where does this token go?* is answered by the **paged allocator**, which hands out blocks
lazily as the sequence actually grows.

Reserving the peak while allocating lazily looks redundant until you drop one of them:

- Reserve the peak, allocate eagerly, and the card holds mostly empty blocks reserved for
  tokens nobody will generate.
- Reserve nothing, allocate lazily, and the server happily admits a hundred requests that
  each fit *today* and cannot all fit at token 300. That failure lands mid-generation,
  after the user has been streamed half an answer, and the only recovery is to preempt
  somebody and throw their cache away.

The second is the expensive mistake, and it is the one that looks correct in a load test
with short answers.

**Preemption** is the escape hatch for when reservations are nonetheless wrong -- a model
reloaded with a different dtype, a pool resized under a running server. It evicts the
*newest* request, because that is the one with the least invested and the one whose user
has been waiting the shortest time. Evicting the oldest maximizes total work thrown away.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agentdesk.serving.blocks import BLOCK_TOKENS, BlockAllocator, OutOfBlocks, blocks_needed
from agentdesk.serving.memory import Budget, ModelSpec, kv_bytes_per_token


class Verdict(StrEnum):
    """Why a request was or was not admitted."""

    ADMITTED = "admitted"
    #: Would fit on an empty server, but not alongside what is already running.
    NO_CAPACITY = "no_capacity"
    #: Would not fit on an empty server either. Retrying will never help.
    TOO_LARGE = "too_large"


@dataclass(frozen=True)
class Request:
    """One generation request.

    Attributes:
        request_id: Unique identifier.
        prompt_tokens: Length of the prompt.
        max_new_tokens: Most tokens it may generate. This is a **commitment**: the
            scheduler reserves against it, and generation stops there.
    """

    request_id: str
    prompt_tokens: int
    max_new_tokens: int

    @property
    def peak_tokens(self) -> int:
        """Tokens cached at this request's largest moment."""
        return self.prompt_tokens + self.max_new_tokens


@dataclass(frozen=True)
class Admission:
    """The scheduler's answer to one admission request.

    Attributes:
        verdict: What was decided.
        request_id: Which request.
        reserved_blocks: Blocks set aside, zero if refused.
        detail: Human-readable reason, for logs and for the ``/serving/plan`` endpoint.
    """

    verdict: Verdict
    request_id: str
    reserved_blocks: int = 0
    detail: str = ""

    @property
    def admitted(self) -> bool:
        """Whether the request may start."""
        return self.verdict is Verdict.ADMITTED


@dataclass
class _Running:
    """Scheduler-side state for an admitted request."""

    request: Request
    reserved_blocks: int
    generated: int = 0
    admitted_seq: int = 0


class Scheduler:
    """Admission control over a paged KV cache.

    Args:
        spec: The served model.
        budget: How the card divides up; its ``kv_available`` sets the pool size.
        allocator: Block pool. Built from the budget when omitted.
    """

    def __init__(
        self,
        spec: ModelSpec,
        *,
        budget: Budget,
        allocator: BlockAllocator | None = None,
    ) -> None:
        self.spec = spec
        self.budget = budget
        self.block_bytes = kv_bytes_per_token(spec) * BLOCK_TOKENS
        total_blocks = budget.kv_available // self.block_bytes
        if total_blocks <= 0:
            raise ValueError(
                f"{budget.kv_available} bytes of KV budget does not hold one "
                f"{self.block_bytes}-byte block"
            )
        self.allocator = allocator or BlockAllocator(total_blocks)
        self._running: dict[str, _Running] = {}
        self._admitted_count = 0
        #: Requests preempted and awaiting a retry, newest first.
        self.preempted: list[Request] = []

    @property
    def total_blocks(self) -> int:
        """Blocks in the pool."""
        return self.allocator.total_blocks

    @property
    def reserved_blocks(self) -> int:
        """Blocks promised to running requests, whether or not yet written."""
        return sum(state.reserved_blocks for state in self._running.values())

    @property
    def spare_blocks(self) -> int:
        """Blocks neither reserved nor held. What admission control has left to spend."""
        return self.total_blocks - self.reserved_blocks

    @property
    def running(self) -> tuple[str, ...]:
        """Ids of requests currently generating, in admission order."""
        return tuple(
            state.request.request_id
            for state in sorted(self._running.values(), key=lambda s: s.admitted_seq)
        )

    def admit(self, request: Request) -> Admission:
        """Decide whether a request may start, reserving its peak if so.

        Args:
            request: The request to consider.

        Returns:
            The :class:`Admission`. Check ``verdict`` rather than truthiness when you
            care *why* -- ``TOO_LARGE`` means stop retrying, ``NO_CAPACITY`` means queue.
        """
        if request.request_id in self._running:
            raise ValueError(f"{request.request_id!r} is already running")

        needed = blocks_needed(request.peak_tokens)

        if needed > self.total_blocks:
            return Admission(
                verdict=Verdict.TOO_LARGE,
                request_id=request.request_id,
                detail=(
                    f"peak of {request.peak_tokens} tokens needs {needed} blocks; "
                    f"the pool only has {self.total_blocks}"
                ),
            )

        if needed > self.spare_blocks:
            return Admission(
                verdict=Verdict.NO_CAPACITY,
                request_id=request.request_id,
                detail=(
                    f"needs {needed} blocks, {self.spare_blocks} unreserved "
                    f"({len(self._running)} running)"
                ),
            )

        self.allocator.allocate(request.request_id, tokens=request.prompt_tokens)
        self._admitted_count += 1
        self._running[request.request_id] = _Running(
            request=request,
            reserved_blocks=needed,
            admitted_seq=self._admitted_count,
        )
        return Admission(
            verdict=Verdict.ADMITTED,
            request_id=request.request_id,
            reserved_blocks=needed,
            detail=f"reserved {needed} blocks for a peak of {request.peak_tokens} tokens",
        )

    def decode_step(self) -> tuple[str, ...]:
        """Generate one token for every running request.

        Returns:
            Ids of requests that reached ``max_new_tokens`` on this step. They have
            already been completed and their blocks returned.

        Raises:
            OutOfBlocks: If a token cannot be placed even after preemption. With correct
                reservations this is unreachable, which is the point of reserving.
        """
        finished: list[str] = []
        for request_id in self.running:
            # Re-read rather than trusting the snapshot: preempting to make room for one
            # request can remove another that this loop was about to serve.
            state = self._running.get(request_id)
            if state is None:
                continue
            try:
                self.allocator.append_token(request_id)
            except OutOfBlocks:
                # Never evict the request we are trying to serve -- that frees its blocks
                # and the retry then fails on an unknown sequence, turning "out of memory"
                # into a confusing KeyError.
                if self._preempt_newest(exclude=request_id) is None:
                    raise
                self.allocator.append_token(request_id)
            state.generated += 1
            if state.generated >= state.request.max_new_tokens:
                finished.append(request_id)

        for request_id in finished:
            self.complete(request_id)
        return tuple(finished)

    def complete(self, request_id: str) -> None:
        """Finish a request, releasing both its reservation and its blocks.

        Both halves matter and they fail differently. Dropping the reservation without
        freeing the blocks leaks physical capacity -- the pool shrinks for the life of
        the process. Freeing the blocks without dropping the reservation leaks the
        *budget* -- memory is available and admission control refuses to spend it.

        Raises:
            KeyError: If no such request is running.
        """
        if request_id not in self._running:
            raise KeyError(request_id)
        self.allocator.free(request_id)
        del self._running[request_id]

    def _preempt_newest(self, *, exclude: str | None = None) -> str | None:
        """Evict the most recently admitted request and queue it for retry.

        Args:
            exclude: A request that must not be chosen, normally the one whose token
                prompted the eviction.

        Returns:
            The evicted id, or ``None`` if there was nobody eligible -- in which case the
            caller is out of options and should let the :class:`OutOfBlocks` propagate.
        """
        candidates = [
            state for state in self._running.values() if state.request.request_id != exclude
        ]
        if not candidates:
            return None
        newest = max(candidates, key=lambda state: state.admitted_seq)
        request_id = newest.request.request_id
        self.allocator.free(request_id)
        del self._running[request_id]
        self.preempted.insert(0, newest.request)
        return request_id

    def run_to_completion(self, request: Request) -> Admission:
        """Admit a request and generate its whole answer. Convenience for tests and the CLI.

        Returns:
            The admission decision. If it was refused, nothing was generated.
        """
        admission = self.admit(request)
        if not admission.admitted:
            return admission
        while request.request_id in self._running:
            self.decode_step()
        return admission

    def snapshot(self) -> dict:
        """Return the scheduler's state, for ``/serving/plan`` and the CLI."""
        return {
            "model": str(self.spec),
            "total_blocks": self.total_blocks,
            "block_tokens": BLOCK_TOKENS,
            "block_bytes": self.block_bytes,
            "reserved_blocks": self.reserved_blocks,
            "spare_blocks": self.spare_blocks,
            "used_blocks": self.allocator.used_blocks,
            "free_blocks": self.allocator.free_blocks,
            "running": list(self.running),
            "preempted": [r.request_id for r in self.preempted],
        }
