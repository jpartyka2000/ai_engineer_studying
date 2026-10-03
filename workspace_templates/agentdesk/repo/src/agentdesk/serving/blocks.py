"""A paged KV cache allocator.

**Why pages rather than one contiguous slab per sequence.**

Reserving ``max_context`` up front for every sequence is simple and wastes most of the
card: a request that asks for 4096 tokens and answers in 80 has held the other 4016 the
whole time. Worse, contiguous reservations fragment -- after a few hundred requests of
varying sizes there is plenty of free memory and no single free run large enough to serve
anybody, so throughput collapses while the dashboard reports the card half empty.

Paging fixes both. The cache is a pool of fixed-size blocks, a sequence holds a list of
them, and a sequence grows by taking one more block when its current one fills. Any free
block will do, so fragmentation stops being a thing that can happen.

**The accounting is the whole job.** Blocks are only returned by :meth:`BlockAllocator.free`,
and a code path that finishes a request without calling it leaks capacity permanently --
no error, no crash, just a server that admits fewer and fewer requests until it admits
none. :meth:`BlockAllocator.check_invariants` exists so that failure has somewhere to be
caught.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Tokens per block. 16 is the usual starting point: large enough that bookkeeping is
#: cheap, small enough that the last partly-filled block of a short answer wastes little.
BLOCK_TOKENS: int = 16


class OutOfBlocks(RuntimeError):
    """Raised when the pool cannot satisfy an allocation.

    Expected under load and not a bug by itself -- it is the signal admission control
    exists to act on. A bug is reaching it while blocks are sitting leaked.
    """


class UnknownSequence(KeyError):
    """Raised when an operation names a sequence the allocator is not holding."""


def blocks_needed(tokens: int) -> int:
    """Return how many blocks hold ``tokens`` tokens.

    Ceiling division: 17 tokens need two blocks, not one and a sixteenth. Flooring here
    is an off-by-one that only shows up on sequences whose length is not a multiple of
    the block size, which is almost all of them, but it shows up as a single overwritten
    token rather than an error.
    """
    if tokens < 0:
        raise ValueError("tokens cannot be negative")
    return (tokens + BLOCK_TOKENS - 1) // BLOCK_TOKENS


@dataclass
class Sequence:
    """One sequence's hold on the pool.

    Attributes:
        seq_id: Caller's identifier.
        blocks: Block indices held, in order.
        tokens: Tokens currently cached.
    """

    seq_id: str
    blocks: list[int] = field(default_factory=list)
    tokens: int = 0

    @property
    def capacity(self) -> int:
        """Tokens this sequence can hold before it needs another block."""
        return len(self.blocks) * BLOCK_TOKENS


class BlockAllocator:
    """A fixed pool of KV cache blocks.

    Args:
        total_blocks: Blocks in the pool, set by dividing the KV budget by the block size.
    """

    def __init__(self, total_blocks: int) -> None:
        if total_blocks <= 0:
            raise ValueError("a pool needs at least one block")
        self.total_blocks = total_blocks
        #: Free block indices. A list used as a stack: the most recently freed block is
        #: reused first, which keeps the working set small.
        self._free: list[int] = list(range(total_blocks))
        self._sequences: dict[str, Sequence] = {}

    @property
    def free_blocks(self) -> int:
        """Blocks available right now."""
        return len(self._free)

    @property
    def used_blocks(self) -> int:
        """Blocks currently held by sequences."""
        return self.total_blocks - len(self._free)

    @property
    def active_sequences(self) -> int:
        """How many sequences hold at least one block."""
        return len(self._sequences)

    def allocate(self, seq_id: str, *, tokens: int) -> Sequence:
        """Reserve enough blocks for a sequence's prompt.

        Args:
            seq_id: Unique identifier.
            tokens: Prompt length in tokens.

        Returns:
            The new :class:`Sequence`.

        Raises:
            OutOfBlocks: If the pool cannot cover it. Nothing is allocated in that case --
                a partial allocation would leak the blocks taken before the failure.
            ValueError: If ``seq_id`` is already held.
        """
        if seq_id in self._sequences:
            raise ValueError(f"sequence {seq_id!r} is already allocated")

        needed = blocks_needed(tokens)
        if needed > len(self._free):
            raise OutOfBlocks(
                f"{seq_id!r} needs {needed} blocks, {len(self._free)} free"
            )

        blocks = [self._free.pop() for _ in range(needed)]
        sequence = Sequence(seq_id=seq_id, blocks=blocks, tokens=tokens)
        self._sequences[seq_id] = sequence
        return sequence

    def append_token(self, seq_id: str) -> Sequence:
        """Account for one more generated token, taking another block if needed.

        Returns:
            The updated :class:`Sequence`.

        Raises:
            UnknownSequence: If this sequence is not allocated.
            OutOfBlocks: If a new block is needed and none is free. The sequence keeps
                what it already holds; the caller must preempt somebody or fail the
                request.
        """
        sequence = self._sequences.get(seq_id)
        if sequence is None:
            raise UnknownSequence(seq_id)

        if sequence.tokens + 1 > sequence.capacity:
            if not self._free:
                raise OutOfBlocks(
                    f"{seq_id!r} needs another block at token {sequence.tokens + 1}, "
                    "pool is empty"
                )
            sequence.blocks.append(self._free.pop())
        sequence.tokens += 1
        return sequence

    def free(self, seq_id: str) -> int:
        """Return a sequence's blocks to the pool.

        **Every** path that finishes a sequence must reach this, including the ones that
        finish by raising. Blocks are not reference counted and nothing reclaims them
        later; a missed call is capacity gone for the life of the process.

        Args:
            seq_id: The sequence to release.

        Returns:
            How many blocks came back.

        Raises:
            UnknownSequence: If this sequence is not allocated.
        """
        sequence = self._sequences.pop(seq_id, None)
        if sequence is None:
            raise UnknownSequence(seq_id)
        self._free.extend(sequence.blocks)
        return len(sequence.blocks)

    def holds(self, seq_id: str) -> bool:
        """Return whether a sequence currently holds blocks."""
        return seq_id in self._sequences

    def sequence(self, seq_id: str) -> Sequence:
        """Return one sequence's state.

        Raises:
            UnknownSequence: If this sequence is not allocated.
        """
        sequence = self._sequences.get(seq_id)
        if sequence is None:
            raise UnknownSequence(seq_id)
        return sequence

    def check_invariants(self) -> None:
        """Assert the pool's books balance.

        Three things must hold at all times, and each corresponds to a real failure:

        - every block is either free or held exactly once (double-allocation)
        - free plus held equals the total (a leak)
        - no sequence holds fewer blocks than its token count needs (silent overwrite)

        Raises:
            AssertionError: Naming which invariant broke.
        """
        held = [block for sequence in self._sequences.values() for block in sequence.blocks]
        all_blocks = sorted(held + self._free)

        duplicates = len(held) != len(set(held))
        assert not duplicates, "a block is held by more than one sequence"
        assert all_blocks == list(range(self.total_blocks)), (
            f"blocks have leaked: {len(all_blocks)} accounted for, "
            f"{self.total_blocks} expected"
        )
        for sequence in self._sequences.values():
            assert sequence.capacity >= sequence.tokens, (
                f"{sequence.seq_id!r} holds {len(sequence.blocks)} blocks for "
                f"{sequence.tokens} tokens"
            )
