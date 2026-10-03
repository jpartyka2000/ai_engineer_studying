"""The model, recorded.

No live API call exists anywhere in this service. Every decision is looked up in
``fixtures/llm_cassettes/`` and a miss is an **error**, never a fallback to the network.

**The key, and why it is shaped the way it is.**

    sha256(model | tools_digest | observations_digest | user_message | context_digest)

Each part earns its place, and one is conspicuously absent.

``tools_digest``
    Covers the tools' **names, parameters and types** -- their contract. It deliberately
    excludes their prose descriptions. Changing what a tool *does* must invalidate the
    recordings; rewording what it is *called* must not, or nobody can improve a
    description without re-recording the suite.

``observations_digest``
    Covers the tool results **as the model will actually see them**, read back out of the
    message list rather than taken from the caller's bookkeeping. This is what makes a
    loop recordable: with nothing observed the model asks for a tool, having seen that
    tool's output it asks for the next, and having seen both it answers. Progress *is*
    the key moving.

    It also makes one bug self-announcing. A tool result appended under the wrong role is
    not an observation -- the digest does not change -- so the key does not change, so the
    model asks for the same tool again. The loop circles rather than advancing, which is
    exactly what the real failure looks like.

``context_digest``
    Covers the **raw** customer text the question concerns -- the bytes as the customer
    typed them, not as the prompt renders them. Two agents asking the same question about
    two different tickets are two different conversations and must key differently. Doing
    this with a separate digest, rather than by letting the fenced block fall into
    ``user_message``, keeps the key independent of how the fence is formatted: improving
    the fence must not invalidate every recording in the repository.

**The assembled prompt is not in the key.** That is the most consequential choice here.
Keying on prompt bytes would mean any rewording -- a clearer instruction, a reordered
rule, a fixed typo -- turned every request into a cassette miss. Prompt *structure* is
checked directly instead, by assertions over the assembled string in
``tests/test_prompt.py``. The cost, stated plainly: this client cannot tell you whether a
rewritten instruction produces a better answer, because the answer is fixed. It tells you
whether the agent asked for the right things, in the right order, and stopped when it
should.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

from agentdesk.llm.types import Decision, Message, ToolCall
from agentdesk.obs import model_span

logger = logging.getLogger(__name__)

#: Cassette format version. Bumped when the on-disk shape changes, so an old fixture set
#: fails loudly rather than being half-understood by new code.
CASSETTE_VERSION = 1

#: How many times one key may be served in a single process before the client decides the
#: caller is stuck.
#:
#: This is a **test ergonomics** decision as much as a safety one. A loop with no step
#: budget does not fail -- it hangs, and a hung test tells you nothing and blocks CI until
#: somebody kills it. Refusing to serve the same key a thirteenth time converts that hang
#: into a named error with a stack trace pointing at the loop.
RUNAWAY_LIMIT = 12

#: How many tool results a single conversation may carry before the client refuses it.
#:
#: A second circuit breaker, and it catches a different failure from :data:`RUNAWAY_LIMIT`.
#: That one catches an agent stuck on one state -- the same key over and over. This one
#: catches an agent that is *moving* and never stopping: each round observes something
#: new, so every key is different, and nothing about repetition would ever notice.
#:
#: Set above ``max_agent_steps`` so a healthy run never meets it. A real deployment has
#: this limit too, in the gateway, for the same reason: the bill.
MAX_OBSERVATIONS = 8


class CassetteMissError(LookupError):
    """Raised when no recorded decision exists for a key.

    Deliberately not a fallback. The ways to reach this are a conversation nobody
    recorded, and a change to a tool's *contract* that moved every key -- both of which
    want a loud failure naming the key, not a call to an API that will bill somebody.
    """


class RunawayLoopError(RuntimeError):
    """Raised when one key is requested more times than any healthy run would need.

    Always a caller bug: the agent is asking the same question of the same state and
    expecting a different answer.
    """


def tools_digest(tools: Iterable) -> str:
    """Return a digest of the tool **contracts**.

    Args:
        tools: Objects exposing ``name`` and ``parameters`` -- in practice
            :class:`~agentdesk.assistant.registry.ToolSpec`.

    Returns:
        A 16-character digest, short because it appears in error messages that humans read.
    """
    contract = [
        {
            "name": tool.name,
            "parameters": {
                param.name: {"type": param.type, "required": param.required}
                for param in tool.parameters
            },
        }
        for tool in sorted(tools, key=lambda t: t.name)
    ]
    blob = json.dumps(contract, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def observations_digest(messages: Sequence[Message]) -> str:
    """Return a digest of the tool results visible in a conversation.

    **Reads the message list rather than trusting a caller's count.** That is the whole
    point: the question being answered is "what has the model been shown?", and only the
    messages can answer it.

    Args:
        messages: The conversation so far.

    Returns:
        A 16-character digest. The empty conversation has a stable digest of its own, so
        the first turn is as recordable as any other.
    """
    observed = [
        {"name": message.name, "content": message.content}
        for message in messages
        if message.role == "tool"
    ]
    blob = json.dumps(observed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def context_digest(raw_context: str | None) -> str:
    """Return a digest of the raw customer text a question concerns.

    Args:
        raw_context: The text exactly as the customer wrote it, or ``None``.

    Returns:
        A 16-character digest; a fixed sentinel when there is no context, so "no ticket"
        is a stable state rather than an empty string that could collide with one.
    """
    if raw_context is None:
        return "no-context"
    return hashlib.sha256(raw_context.encode("utf-8")).hexdigest()[:16]


def cassette_key(
    *, model: str, tools: str, observations: str, user_message: str, context: str
) -> str:
    """Return the cassette key for one decision.

    Parts are joined with a NUL, which cannot occur in any of them, so no two different
    requests can collide by concatenation.
    """
    joined = "\x00".join([model, tools, observations, user_message, context])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class RecordedClient:
    """Replays recorded decisions.

    Args:
        cassette_dir: Directory of ``<key>.json`` files.
        model: Model identifier, part of every key.
        runaway_limit: Times one key may be served before :class:`RunawayLoopError`.
    """

    def __init__(
        self,
        cassette_dir: Path,
        *,
        model: str,
        runaway_limit: int = RUNAWAY_LIMIT,
        max_observations: int = MAX_OBSERVATIONS,
    ) -> None:
        self.cassette_dir = Path(cassette_dir)
        self.model = model
        self.runaway_limit = runaway_limit
        self.max_observations = max_observations
        self._served: Counter[str] = Counter()

    def decide(
        self, *, messages: Sequence[Message], tools: str, context: str | None = None
    ) -> Decision:
        """Return the recorded decision for this conversation.

        Args:
            messages: The conversation so far, including the system message.
            tools: The digest from :func:`tools_digest`.
            context: Raw customer text this conversation concerns, if any.

        Returns:
            The recorded :class:`~agentdesk.llm.types.Decision`.

        Raises:
            CassetteMissError: If nothing is recorded for this state.
            RunawayLoopError: If this exact state has already been served
                ``runaway_limit`` times, which means the caller is not making progress.
            ValueError: If the conversation contains no user message.
        """
        user_message = _first_user_message(messages)

        observed = sum(1 for message in messages if message.role == "tool")
        if observed > self.max_observations:
            raise RunawayLoopError(
                f"this conversation already carries {observed} tool results, over the "
                f"limit of {self.max_observations}. The agent is still making progress "
                "and still not stopping: nothing is bounding the number of steps."
            )

        key = cassette_key(
            model=self.model,
            tools=tools,
            observations=observations_digest(messages),
            user_message=user_message,
            context=context_digest(context),
        )

        self._served[key] += 1
        if self._served[key] > self.runaway_limit:
            raise RunawayLoopError(
                f"key {key[:12]} has been served {self._served[key]} times. The agent is "
                "asking the same question of the same state: either a tool result is not "
                "reaching the conversation, or nothing is bounding the number of steps."
            )

        with model_span(key):
            path = self.cassette_dir / f"{key}.json"
            if not path.is_file():
                raise CassetteMissError(
                    f"no cassette for key {key} "
                    f"(message: {user_message[:60]!r}, "
                    f"{observations_digest(messages)} observed). Either this conversation "
                    "was never recorded, or a tool's contract changed and every key moved "
                    "with it. Re-record with `make cassettes`; do not add a network call."
                )
            payload = _load(path)

        if payload.get("version") != CASSETTE_VERSION:
            raise CassetteMissError(
                f"cassette {key} is version {payload.get('version')!r}, "
                f"expected {CASSETTE_VERSION}"
            )

        return Decision(
            tool_calls=tuple(
                ToolCall(id=c["id"], name=c["name"], arguments=c.get("arguments", {}))
                for c in payload.get("tool_calls", ())
            ),
            text=payload.get("text", ""),
            citations=tuple(payload.get("citations", ())),
        )

    def served(self, key: str) -> int:
        """Return how many times one key has been served. Used by the loop tests."""
        return self._served[key]

    def keys(self) -> list[str]:
        """Return every recorded key, sorted. Used by the consistency test."""
        return sorted(path.stem for path in self.cassette_dir.glob("*.json"))


def _first_user_message(messages: Sequence[Message]) -> str:
    """Return the content of the first user message.

    The *first*, not the last: within one agent run the user's question does not change,
    and taking the last would make the key drift if anything ever appended on the user's
    behalf.
    """
    for message in messages:
        if message.role == "user":
            return message.content
    raise ValueError("a conversation needs a user message")


@lru_cache(maxsize=512)
def _load(path: Path) -> dict:
    """Read and parse one cassette.

    Cached by path. Safe only because cassettes are immutable fixtures -- if they ever
    become writable at runtime, this has to go.
    """
    return json.loads(path.read_text(encoding="utf-8"))
