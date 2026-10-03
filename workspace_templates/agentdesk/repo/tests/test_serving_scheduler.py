"""Admission control.

The central claim this file defends: **with correct reservations, preemption never
happens.** Preemption is the recovery path for a planner that was wrong, so a server that
preempts under ordinary load is telling you its admission arithmetic is broken, not that
it is busy.
"""

from __future__ import annotations

import pytest

from agentdesk.serving import DESK_8B
from agentdesk.serving.blocks import BlockAllocator
from agentdesk.serving.memory import plan_budget
from agentdesk.serving.scheduler import Request, Scheduler, Verdict

GIB = 1024**3


@pytest.fixture
def scheduler() -> Scheduler:
    """A scheduler over the real served model and a real 24 GiB card."""
    return Scheduler(DESK_8B, budget=plan_budget(DESK_8B, vram_bytes=24 * GIB))


@pytest.fixture
def small() -> Scheduler:
    """A deliberately tiny pool, so capacity limits are reachable in a test."""
    budget = plan_budget(DESK_8B, vram_bytes=24 * GIB)
    return Scheduler(DESK_8B, budget=budget, allocator=BlockAllocator(total_blocks=20))


def fill(scheduler: Scheduler, *, prompt: int = 900, new: int = 200) -> int:
    """Admit requests until refused. Returns how many got in."""
    admitted = 0
    while True:
        request = Request(f"r{admitted}", prompt_tokens=prompt, max_new_tokens=new)
        if not scheduler.admit(request).admitted:
            return admitted
        admitted += 1


def drain(scheduler: Scheduler, *, limit: int = 1000) -> int:
    """Decode until nothing is running. Returns the number of steps taken."""
    steps = 0
    while scheduler.running and steps < limit:
        scheduler.decode_step()
        steps += 1
    return steps


def test_an_admitted_request_reserves_its_peak(scheduler: Scheduler) -> None:
    admission = scheduler.admit(Request("a", prompt_tokens=900, max_new_tokens=200))
    assert admission.verdict is Verdict.ADMITTED
    # 1100 tokens at 16 per block.
    assert admission.reserved_blocks == 69
    assert scheduler.reserved_blocks == 69


def test_a_request_larger_than_the_pool_is_refused_permanently(small: Scheduler) -> None:
    """``TOO_LARGE`` and ``NO_CAPACITY`` are different answers and callers act on them
    differently: one means queue and retry, the other means stop."""
    admission = small.admit(Request("huge", prompt_tokens=4000, max_new_tokens=1000))
    assert admission.verdict is Verdict.TOO_LARGE
    assert not admission.admitted


def test_a_request_that_would_fit_alone_is_queued_not_rejected(small: Scheduler) -> None:
    assert small.admit(Request("a", prompt_tokens=150, max_new_tokens=50)).admitted
    second = small.admit(Request("b", prompt_tokens=150, max_new_tokens=50))
    assert second.verdict is Verdict.NO_CAPACITY


def test_a_full_batch_runs_to_completion_without_preempting(scheduler: Scheduler) -> None:
    """**The property ex-059 turns on, stated directly.**

    Fill the server, then let every request generate its whole answer. Reservations sized
    on the peak make this safe by construction. Reservations sized on the prompt admit
    more requests than can coexist at token 200, and the server starts throwing work away
    mid-generation -- which shows up here, and nowhere in a load test with short answers.
    """
    admitted = fill(scheduler)
    assert admitted > 1, "the fixture must admit several requests for this to prove anything"

    drain(scheduler)

    assert scheduler.preempted == [], (
        f"{len(scheduler.preempted)} request(s) were preempted; admission control "
        "allowed more work onto the card than could finish"
    )
    scheduler.allocator.check_invariants()


def test_completion_returns_capacity_for_the_next_request(scheduler: Scheduler) -> None:
    """**The property ex-060 turns on, stated directly.**

    Churn, then assert the server is exactly as capable as it was. A path that finishes a
    request without returning its blocks does not raise -- it just means the next hour
    admits fewer requests than this one, and the hour after that fewer still.
    """
    before = fill(scheduler)
    drain(scheduler)

    assert scheduler.allocator.free_blocks == scheduler.total_blocks
    assert scheduler.spare_blocks == scheduler.total_blocks
    assert scheduler.running == ()

    after = fill(scheduler)
    assert after == before, (
        f"the server admitted {before} requests and then only {after}; "
        "capacity did not come back"
    )


def test_reservations_and_physical_blocks_are_different_numbers(scheduler: Scheduler) -> None:
    """A newly admitted request has reserved its peak and written only its prompt.

    If these two were equal the design would be eager allocation wearing paging's name,
    and the card would hold blocks for tokens nobody has generated.
    """
    scheduler.admit(Request("a", prompt_tokens=900, max_new_tokens=200))
    assert scheduler.reserved_blocks == 69
    assert scheduler.allocator.used_blocks == 57


def test_decode_advances_every_running_request(scheduler: Scheduler) -> None:
    scheduler.admit(Request("a", prompt_tokens=100, max_new_tokens=3))
    scheduler.admit(Request("b", prompt_tokens=100, max_new_tokens=3))
    assert scheduler.decode_step() == ()
    assert scheduler.decode_step() == ()
    assert set(scheduler.decode_step()) == {"a", "b"}
    assert scheduler.running == ()


def test_a_finished_request_is_completed_exactly_once(scheduler: Scheduler) -> None:
    scheduler.admit(Request("a", prompt_tokens=100, max_new_tokens=1))
    assert scheduler.decode_step() == ("a",)
    with pytest.raises(KeyError):
        scheduler.complete("a")


def test_preemption_keeps_the_books_balanced(small: Scheduler) -> None:
    """Prove the recovery path itself is sound, so a later failure is never ambiguous.

    Forced by shrinking reservations behind the scheduler's back -- the same state a
    mis-sized reservation produces, reached deliberately so the preemption branch is
    covered rather than merely present.
    """
    small.admit(Request("a", prompt_tokens=150, max_new_tokens=100))
    for state in small._running.values():
        state.reserved_blocks = 1
    small.admit(Request("b", prompt_tokens=150, max_new_tokens=100))

    drain(small)

    assert small.preempted, "the forced shortage should have evicted somebody"
    small.allocator.check_invariants()
    assert small.allocator.free_blocks == small.total_blocks


def test_the_newest_request_is_the_one_evicted(small: Scheduler) -> None:
    """Evicting the oldest throws away the most work and punishes the longest wait."""
    small.admit(Request("first", prompt_tokens=150, max_new_tokens=100))
    for state in small._running.values():
        state.reserved_blocks = 1
    small.admit(Request("second", prompt_tokens=150, max_new_tokens=100))

    drain(small)

    assert [r.request_id for r in small.preempted] == ["second"]


def test_snapshot_reports_both_kinds_of_capacity(scheduler: Scheduler) -> None:
    scheduler.admit(Request("a", prompt_tokens=900, max_new_tokens=200))
    snapshot = scheduler.snapshot()
    assert snapshot["reserved_blocks"] == 69
    assert snapshot["used_blocks"] == 57
    assert snapshot["running"] == ["a"]
