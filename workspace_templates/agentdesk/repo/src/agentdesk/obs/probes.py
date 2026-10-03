"""Instrumentation that makes a latency claim checkable by **cause** rather than by clock.

**Why this module exists instead of a benchmark.**

The obvious way to test "the assistant must not slow the ticket desk down" is to measure
p95 and assert a threshold. We tried that and deleted it. Two reasons:

1. A wall-clock threshold in CI is a coin flip. It fails on a noisy runner and passes on a
   quiet one, so the signal is about the machine, not the code.
2. It does not say what is wrong. "p95 is 900ms" sends you to a profiler. "a database
   connection was held open across a model call" sends you to the line.

So every latency guarantee in this codebase is expressed as a **structural** property of
one request, and those properties are exact:

- no pooled connection is checked out while a model call is in flight (:func:`connections_held_across_model_calls`)
- model calls do not run on the event loop thread (:func:`model_call_threads`)
- a list endpoint makes a number of model calls that does not grow with the page size (:meth:`Trace.count`)

Benchmarks still exist -- ``agentdesk bench`` prints real numbers, and you should watch
them move -- but **nothing passes or fails on a timing assertion**.

**Scope.** The trace is held in a :class:`~contextvars.ContextVar`, so concurrent requests
do not see each other's events. :func:`asyncio.to_thread` copies the context into the
worker thread, which is what lets a model call running off-loop still record into the
trace that started on it.
"""

from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

#: Event kinds. Strings rather than an enum because they are also matched in tests and in
#: the CLI's trace dump, where a bare name reads better than ``EventKind.DB_ACQUIRE``.
DB_ACQUIRE = "db.acquire"
DB_RELEASE = "db.release"
MODEL_START = "llm.start"
MODEL_END = "llm.end"
TOOL_CALL = "tool.call"


@dataclass(frozen=True)
class Event:
    """One recorded moment.

    Attributes:
        kind: One of the module-level kind constants.
        payload: Kind-specific detail. Kept as a plain dict so adding a field to one
            event kind does not require touching every other.
        thread: The OS thread the event was recorded on. This is the whole mechanism
            behind the event-loop check: an identifier, not a duration.
        seq: Monotonic position within the trace. Ordering matters for the
            held-across-a-model-call analysis and list order alone is not enough once
            threads are involved.
    """

    kind: str
    payload: dict
    thread: int
    seq: int


@dataclass
class Trace:
    """An ordered record of what one request did.

    Not thread-safe in the strict sense and does not need to be: appends to a list are
    atomic under the GIL, and nothing here reads the events until the request is over.
    """

    events: list[Event] = field(default_factory=list)
    _next_seq: int = 0

    def record(self, kind: str, **payload: object) -> None:
        """Append an event of ``kind`` carrying ``payload``."""
        self.events.append(
            Event(
                kind=kind,
                payload=dict(payload),
                thread=threading.get_ident(),
                seq=self._next_seq,
            )
        )
        self._next_seq += 1

    def of(self, kind: str) -> list[Event]:
        """Return every event of one kind, in order."""
        return [event for event in self.events if event.kind == kind]

    def count(self, kind: str) -> int:
        """Return how many events of one kind were recorded."""
        return len(self.of(kind))


#: The active trace. ``None`` means nobody is watching, which is the production default --
#: recording is opt-in so the probes cost nothing when unused.
_ACTIVE: contextvars.ContextVar[Trace | None] = contextvars.ContextVar(
    "agentdesk_trace", default=None
)


@contextmanager
def tracing() -> Iterator[Trace]:
    """Record everything that happens in this block.

    Yields:
        The :class:`Trace`, readable after the block exits.
    """
    trace = Trace()
    token = _ACTIVE.set(trace)
    try:
        yield trace
    finally:
        _ACTIVE.reset(token)


def record(kind: str, **payload: object) -> None:
    """Record an event if anything is listening, otherwise do nothing."""
    trace = _ACTIVE.get()
    if trace is not None:
        trace.record(kind, **payload)


@contextmanager
def db_span(token: str) -> Iterator[None]:
    """Bracket the period a pooled connection is checked out.

    Args:
        token: Identifies this checkout. Reused tokens would make an interleaved trace
            ambiguous, so callers pass something unique per acquisition.
    """
    record(DB_ACQUIRE, token=token)
    try:
        yield
    finally:
        # In a ``finally`` so an exception mid-query does not leave the analysis believing
        # the connection is still held, which would report a false offender.
        record(DB_RELEASE, token=token)


@contextmanager
def model_span(key: str) -> Iterator[None]:
    """Bracket one model call."""
    record(MODEL_START, key=key)
    try:
        yield
    finally:
        record(MODEL_END, key=key)


def connections_held_across_model_calls(trace: Trace) -> list[str]:
    """Return the tokens of connections that were open when a model call started.

    This is the exact statement of "do not hold a connection across the model call". A
    pooled connection held for the duration of a one-second generation is one fewer
    connection for the ticket desk, and with a pool of ten and ten concurrent assistant
    requests the desk stops serving entirely while nothing about the desk has changed.

    Args:
        trace: A completed trace.

    Returns:
        Sorted, de-duplicated tokens. Empty is the healthy answer.
    """
    open_tokens: set[str] = set()
    offenders: set[str] = set()
    for event in sorted(trace.events, key=lambda e: e.seq):
        if event.kind == DB_ACQUIRE:
            open_tokens.add(str(event.payload["token"]))
        elif event.kind == DB_RELEASE:
            open_tokens.discard(str(event.payload["token"]))
        elif event.kind == MODEL_START:
            offenders |= open_tokens
    return sorted(offenders)


def model_call_threads(trace: Trace) -> set[int]:
    """Return the thread ids model calls ran on.

    Compared against the caller's own thread to detect a blocking call on the event loop.
    An identifier comparison, so it is deterministic under any CI load -- which a
    "did it take longer than 50ms" probe is not.
    """
    return {event.thread for event in trace.of(MODEL_START)}
