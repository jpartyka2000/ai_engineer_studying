"""The model, recorded.

There is no live API call anywhere in this service. Every generation is looked up in
``fixtures/llm_cassettes/`` and a miss is an **error**, never a fallback to the network.

**The key is the question, not the assembled prompt, and that is the most consequential
decision in this codebase.**

The obvious design keys on everything sent to the model, assembled prompt included. Here
that would be actively harmful, because the assembled prompt embeds the retrieved
passages: *any* change to retrieval -- a different chunk size, a different ranking, one
fewer passage -- changes the prompt, changes the key, and turns every request into a
cassette miss. A retrieval bug would then present as "no recording found" rather than as
a worse answer, which is both useless for diagnosis and wrong about what retrieval bugs
actually do.

Keying on the question means the recorded answer is **what the model says when retrieval
is working**. The consequence, stated plainly: this service cannot measure whether bad
context produces a bad answer, because the answer is fixed. What it measures instead is
everything the answer is built on -- whether the right passages were found, whether the
citations are supported by what was actually retrieved, and whether the system knew to
refuse. Those are functions of the retrieved set, they are exactly what
:mod:`ragqa.eval.metrics` scores, and the pipeline is wired so a retrieval failure
degrades them rather than erroring.

The recorded response therefore carries **both** an answer and the chunk ids the model
claims to have used. The second half is what makes a fabricated citation detectable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

#: Cassette format version. Bumped if the on-disk shape changes, so an old fixture set
#: fails loudly rather than being half-understood by new code.
CASSETTE_VERSION = 1


class CassetteMissError(LookupError):
    """Raised when no recorded response exists for a question.

    Deliberately not a fallback. The two ways to reach this are a question nobody
    recorded an answer for, and an edit to the system prompt that moved every key --
    both of which want a loud failure naming the key, not a call to an API that will
    bill somebody.
    """


@dataclass(frozen=True)
class Generation:
    """One recorded model response.

    Attributes:
        answer: The answer text, exactly as recorded.
        citations: Chunk ids the model claims to have used. **Claims** is the operative
            word: nothing here has verified them, and verifying them against what was
            actually retrieved is the guardrails' job.
        key: The cassette key this came from.
        question: The question, kept so that ``git log -S`` over the fixture directory
            is a useful archaeology tool.
        notes: Why this cassette exists.
    """

    answer: str
    citations: tuple[str, ...] = ()
    key: str = ""
    question: str = ""
    notes: str = ""


def cassette_key(*, model: str, system: str, question: str) -> str:
    """Return the cassette key for a question.

    The three parts are joined with a separator that cannot appear in any of them, so no
    two different requests can collide by concatenation.

    Args:
        model: Model identifier.
        system: System prompt.
        question: The user's question, verbatim.

    Returns:
        A 64-character hex digest.
    """
    joined = "\x00".join([model, system, question])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class RecordedClient:
    """Looks up generations in a cassette directory.

    Args:
        cassette_dir: Directory of ``<key>.json`` files.
        model: Model identifier, part of every key.
    """

    def __init__(self, cassette_dir: Path, *, model: str) -> None:
        self.cassette_dir = Path(cassette_dir)
        self.model = model

    def generate(self, *, system: str, question: str) -> Generation:
        """Return the recorded generation for a question.

        Args:
            system: System prompt.
            question: The user's question.

        Returns:
            The recorded :class:`Generation`.

        Raises:
            CassetteMissError: If nothing is recorded for this exact question.
        """
        key = cassette_key(model=self.model, system=system, question=question)
        path = self.cassette_dir / f"{key}.json"
        if not path.is_file():
            raise CassetteMissError(
                f"no cassette for key {key} (question: {question[:60]!r}). Either this "
                "question was never recorded, or the system prompt changed and every key "
                "moved with it. Re-record with `make cassettes`; do not add a network call."
            )

        payload = _load(path)
        if payload.get("version") != CASSETTE_VERSION:
            raise CassetteMissError(
                f"cassette {key} is version {payload.get('version')!r}, "
                f"expected {CASSETTE_VERSION}"
            )
        return Generation(
            answer=payload["answer"],
            citations=tuple(payload.get("citations", ())),
            key=key,
            question=payload.get("question", question),
            notes=payload.get("notes", ""),
        )

    def keys(self) -> list[str]:
        """Return every recorded key, sorted. Used by the consistency test."""
        return sorted(path.stem for path in self.cassette_dir.glob("*.json"))


@lru_cache(maxsize=512)
def _load(path: Path) -> dict:
    """Read and parse one cassette.

    Cached by path: the eval harness reads the same files once per question per run. Safe
    only because cassettes are immutable fixtures -- if they ever become writable at
    runtime, this has to go.
    """
    return json.loads(path.read_text(encoding="utf-8"))
