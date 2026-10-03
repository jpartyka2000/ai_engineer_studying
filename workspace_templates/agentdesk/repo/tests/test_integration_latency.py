"""What the assistant is allowed to cost the desk.

**Not one assertion in this file looks at a clock, and that is the point.**

The version of this file that measured p95 lasted two weeks. It failed on busy CI runners
and passed on quiet ones, so it got a longer timeout, then another, until it asserted
nothing anybody believed. Worse, when it did fail it sent you to a profiler rather than to
a line.

Every test here names a **mechanism** instead:

- a pooled connection must not be held while a model call is in flight
- a model call must not run on the event loop thread
- the dashboard must make a number of model calls that does not depend on how many
  tickets it shows

Each is exactly true or exactly false, on any machine, under any load. ``agentdesk bench``
still prints real timings for a human to look at; nothing here passes or fails on them.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from agentdesk.assistant import digest
from agentdesk.assistant.recording import Script, ScriptedCall
from agentdesk.assistant.service import draft_reply, summarize_for_intake
from agentdesk.clock import now
from agentdesk.obs import (
    MODEL_START,
    connections_held_across_model_calls,
    model_call_threads,
    tracing,
)
from tests.conftest import ticket_row

pytestmark = pytest.mark.latency


@pytest.fixture
def seeded_pool(fake_pool):
    """A fake pool holding one ticket, so the assistant path has something to read."""
    fake_pool.rows = [ticket_row(ticket_id=1)]
    return fake_pool


@pytest.fixture
def script() -> Script:
    """A one-tool conversation, enough to put a model call between two queries."""
    return Script(
        id="latency",
        question="What should I tell them about the VPN?",
        calls=(ScriptedCall(tool="fact", arguments={"topic": "vpn"}, call_id="c0"),),
        answer="VPN access needs manager approval and is provisioned overnight.",
        citations=("vpn",),
        # Must match the body the fake pool returns: the raw customer text is part of the
        # cassette key, because two tickets asking the same question are two conversations.
        ticket_body="I cannot connect to the VPN since this morning.",
    )


async def test_no_connection_is_held_across_a_model_call(
    seeded_pool, registry, recorder, script
) -> None:
    """**The property ex-056 turns on, stated directly.**

    The pool is ten connections. A generation takes about a second. Hold one across the
    generation and ten concurrent assistant requests own the entire pool -- at which
    point the ticket list, which never asked for an assistant, starts timing out. The
    symptom appears in an endpoint that did not change, which is what makes it expensive
    to find.
    """
    client = recorder(script)

    with tracing() as trace:
        await draft_reply(1, script.question, registry=registry, client=client)

    assert trace.count(MODEL_START) > 0, "the fixture must actually call the model"
    held = connections_held_across_model_calls(trace)
    assert held == [], (
        f"connection(s) {held} were checked out while the model was running; "
        "read, release, generate, then write"
    )


async def test_the_model_call_does_not_run_on_the_event_loop(
    seeded_pool, registry, recorder, script
) -> None:
    """**The property ex-057 turns on, stated directly.**

    A blocking call on the loop thread stops *every* coroutine in the process, including
    endpoints with nothing to do with the assistant and including the health check -- so
    the first symptom is often the orchestrator restarting a container that was fine.

    Thread identity, not elapsed time: exact on any machine, where "did it take longer
    than 50ms" is a coin flip.
    """
    loop_thread = threading.get_ident()
    client = recorder(script)

    with tracing() as trace:
        await draft_reply(1, script.question, registry=registry, client=client)

    threads = model_call_threads(trace)
    assert threads, "the fixture must actually call the model"
    assert loop_thread not in threads, (
        "the model ran on the event loop thread; wrap the blocking call in "
        "asyncio.to_thread so the rest of the process keeps being served"
    )


async def test_the_loop_keeps_running_while_a_draft_is_generated(
    seeded_pool, registry, recorder, script
) -> None:
    """The same property from the outside: other coroutines must still make progress.

    A counter advanced by a cooperating task, not a timer. If the draft blocks the loop,
    the ticker cannot run at all and the count stays at zero -- which is a statement about
    scheduling, not about speed.
    """
    client = recorder(script)
    ticks = 0
    running = True

    async def ticker() -> None:
        nonlocal ticks
        while running:
            ticks += 1
            await asyncio.sleep(0)

    task = asyncio.create_task(ticker())
    await draft_reply(1, script.question, registry=registry, client=client)
    running = False
    await task

    assert ticks > 0, "nothing else ran while the draft was being generated"


async def test_intake_summarization_also_stays_off_the_loop(
    seeded_pool, registry, recorder
) -> None:
    """Intake is the other path that calls a model, and it is on the ticket-creation
    request. The same rule applies and is easy to forget twice."""
    script = Script(
        id="intake",
        question="Summarize this ticket in one line for a queue listing: VPN down",
        calls=(),
        answer="Customer cannot connect to the VPN.",
        ticket_body="I cannot connect",
    )
    client = recorder(script)
    loop_thread = threading.get_ident()

    with tracing() as trace:
        summary = await summarize_for_intake(
            "VPN down", "I cannot connect", registry=registry, client=client
        )

    assert summary == "Customer cannot connect to the VPN."
    assert loop_thread not in model_call_threads(trace)


def test_the_queue_digest_makes_no_model_calls(fake_pool) -> None:
    """**The property ex-058 turns on, stated directly.**

    Summaries are written once, at intake, and read from a column forever after. The
    dashboard regenerating them is one line, renders identically, and turns a 25-row page
    into 25 model calls. Nothing errors; the page is simply slow, in proportion to how
    much work the customer has.

    Asserted as **zero**, not "few". "Few" is how this comes back.
    """
    fake_pool.rows = [ticket_row(ticket_id=index) for index in range(1, 26)]

    with tracing() as trace:
        payload = digest.queue_digest(now=now())

    assert payload["rows"], "the fixture must return rows for this to prove anything"
    assert trace.count(MODEL_START) == 0, (
        f"the dashboard made {trace.count(MODEL_START)} model call(s); summaries come "
        "from the column written at intake"
    )


def test_the_queue_digest_makes_one_database_round_trip(fake_pool) -> None:
    """The same shape of bug on the database side, and the cheaper one to hit first."""
    fake_pool.rows = [ticket_row(ticket_id=index) for index in range(1, 26)]

    digest.queue_digest(now=now())

    assert fake_pool.checkouts == 1, (
        f"{fake_pool.checkouts} connections were checked out to render one page"
    )


def test_a_ticket_with_no_summary_does_not_trigger_a_model_call(fake_pool) -> None:
    """The fallback path is the tempting place to "just generate one".

    Tickets older than the summary column have none, so this is not a hypothetical row --
    it is in the seed data.
    """
    fake_pool.rows = [ticket_row(ticket_id=1, summary=None)]

    with tracing() as trace:
        payload = digest.queue_digest(now=now())

    assert payload["rows"][0]["summary"] == "VPN will not connect"
    assert trace.count(MODEL_START) == 0
