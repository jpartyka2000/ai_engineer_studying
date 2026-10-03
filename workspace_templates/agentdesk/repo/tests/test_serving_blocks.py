"""The paged KV allocator.

The theme is accounting. Almost nothing here is about whether a single allocation works;
it is about whether the books still balance after a few hundred of them, because that is
the only way a block leak is ever visible.
"""

from __future__ import annotations

import pytest

from agentdesk.serving.blocks import (
    BLOCK_TOKENS,
    BlockAllocator,
    OutOfBlocks,
    UnknownSequence,
    blocks_needed,
)


def test_blocks_needed_rounds_up() -> None:
    """17 tokens need two blocks. Flooring here overwrites a token rather than erroring."""
    assert blocks_needed(0) == 0
    assert blocks_needed(1) == 1
    assert blocks_needed(BLOCK_TOKENS) == 1
    assert blocks_needed(BLOCK_TOKENS + 1) == 2


def test_allocation_takes_blocks_and_free_returns_them() -> None:
    pool = BlockAllocator(total_blocks=100)
    pool.allocate("a", tokens=64)
    assert pool.used_blocks == 4
    assert pool.free_blocks == 96

    assert pool.free("a") == 4
    assert pool.free_blocks == 100
    pool.check_invariants()


def test_a_sequence_grows_a_block_at_a_time() -> None:
    pool = BlockAllocator(total_blocks=10)
    sequence = pool.allocate("a", tokens=BLOCK_TOKENS)
    assert len(sequence.blocks) == 1

    pool.append_token("a")  # one past the block boundary
    assert len(pool.sequence("a").blocks) == 2
    pool.check_invariants()


def test_an_allocation_that_cannot_fit_takes_nothing() -> None:
    """A partial allocation would leak whatever it took before giving up."""
    pool = BlockAllocator(total_blocks=4)
    with pytest.raises(OutOfBlocks):
        pool.allocate("big", tokens=BLOCK_TOKENS * 5)
    assert pool.free_blocks == 4
    assert not pool.holds("big")
    pool.check_invariants()


def test_the_same_sequence_cannot_be_allocated_twice() -> None:
    pool = BlockAllocator(total_blocks=10)
    pool.allocate("a", tokens=16)
    with pytest.raises(ValueError, match="already allocated"):
        pool.allocate("a", tokens=16)


def test_operating_on_an_unknown_sequence_raises() -> None:
    pool = BlockAllocator(total_blocks=10)
    with pytest.raises(UnknownSequence):
        pool.append_token("ghost")
    with pytest.raises(UnknownSequence):
        pool.free("ghost")


def test_a_full_pool_refuses_to_grow_a_sequence() -> None:
    pool = BlockAllocator(total_blocks=1)
    pool.allocate("a", tokens=BLOCK_TOKENS)
    with pytest.raises(OutOfBlocks, match="pool is empty"):
        pool.append_token("a")
    # The sequence keeps what it had; this is a signal to preempt, not a corruption.
    assert pool.sequence("a").tokens == BLOCK_TOKENS
    pool.check_invariants()


def test_capacity_survives_many_sequential_sequences() -> None:
    """**The property ex-060 turns on, stated directly.**

    A leak does not raise and does not corrupt anything. It shows up only as a pool that
    is quietly smaller than it was, which is why this asserts the count returns to full
    after churn rather than after a single release.
    """
    pool = BlockAllocator(total_blocks=64)
    for index in range(200):
        pool.allocate(f"seq-{index}", tokens=100)
        for _ in range(20):
            pool.append_token(f"seq-{index}")
        pool.free(f"seq-{index}")

    assert pool.free_blocks == 64, "blocks were not returned to the pool"
    assert pool.active_sequences == 0
    pool.check_invariants()


def test_invariants_catch_a_leak_rather_than_letting_it_run() -> None:
    """Prove the safety net works, by breaking the books behind the allocator's back.

    Without this, ``check_invariants`` could be vacuous -- a method that has never once
    reported a problem is indistinguishable from one that cannot.
    """
    pool = BlockAllocator(total_blocks=8)
    pool.allocate("a", tokens=32)
    pool._sequences.pop("a")  # exactly what forgetting to call free() leaves behind

    with pytest.raises(AssertionError, match="leaked"):
        pool.check_invariants()


def test_invariants_catch_the_same_block_held_twice() -> None:
    pool = BlockAllocator(total_blocks=8)
    pool.allocate("a", tokens=16)
    pool.allocate("b", tokens=16)
    pool.sequence("b").blocks[0] = pool.sequence("a").blocks[0]

    with pytest.raises(AssertionError, match="more than one"):
        pool.check_invariants()


def test_blocks_are_reused_rather_than_exhausted() -> None:
    """Freed blocks must come back into circulation, not merely stop being counted."""
    pool = BlockAllocator(total_blocks=4)
    first = pool.allocate("a", tokens=BLOCK_TOKENS * 4).blocks
    pool.free("a")
    second = pool.allocate("b", tokens=BLOCK_TOKENS * 4).blocks
    assert sorted(first) == sorted(second)
