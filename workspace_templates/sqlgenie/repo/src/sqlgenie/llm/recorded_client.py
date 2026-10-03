"""The model, recorded.

There is no live API call anywhere in this service. Every generation is looked up in
``fixtures/llm_cassettes/`` by a hash of exactly what would have been sent:
``sha256(model | system | prompt)``. A miss is an **error**, never a fallback to the
network -- a test suite that quietly reaches the internet is one that fails differently
on every machine and costs money to run.

**What that buys and what it costs, stated plainly.** It buys determinism: the same
question produces the same SQL on every machine, forever, so a test can assert on the
SQL and a security test can assert on what the SQL *did*. It costs live model quality:
nothing here tells you whether the model is good at text-to-SQL today. That is the right
trade, because live model output cannot be scored anyway, and because the things worth
testing in this service -- prompt assembly, the tenant rewrite, the guards, the audit
trail -- are all downstream of generation and none of them care whether the SQL was
written by a model or a fixture.

**The key is the whole request, which has a consequence worth knowing before you edit
anything.** The prompt embeds the schema section rendered from
:mod:`sqlgenie.nl2sql.catalog`. Change a column name, reorder a table, reword the system
prompt, and every cassette key changes and every lookup misses. That is not fragility,
it is the point: a recorded response is only valid for the exact request that produced
it. ``tests/test_cassettes.py`` asserts the corpus and the cassettes still agree, so the
breakage surfaces as one clear failure rather than as fifty confusing ones.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

#: Cassette format version. Bumped if the on-disk shape changes, so an old fixture set
#: fails loudly rather than being half-understood by new code.
CASSETTE_VERSION = 1


class CassetteMissError(LookupError):
    """Raised when no recorded response exists for a request.

    Deliberately not a fallback. The two ways to reach this are a question nobody has
    recorded an answer for, and an edit to the prompt or the schema that changed every
    key -- and both of those want a loud failure that names the key, not a quiet call to
    an API that will bill somebody.
    """


@dataclass(frozen=True)
class Generation:
    """One recorded model response.

    Attributes:
        sql: The SQL the model produced, exactly as recorded.
        key: The cassette key this came from.
        question: The natural-language question, kept for debugging and so that
            ``git log -S`` over the cassette directory is a useful archaeology tool.
        notes: Why this cassette exists. Attack cassettes say what they are probing.
    """

    sql: str
    key: str
    question: str = ""
    notes: str = ""


def cassette_key(*, model: str, system: str, prompt: str) -> str:
    """Return the cassette key for a request.

    The three parts are joined with a separator that cannot appear in any of them, so
    that no pair of different requests can collide by concatenation -- ``("ab", "c")``
    and ``("a", "bc")`` must not hash the same.

    Args:
        model: Model identifier.
        system: System prompt.
        prompt: User prompt, schema section included.

    Returns:
        A 64-character hex digest.
    """
    joined = "\x00".join([model, system, prompt])
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

    def generate(self, *, system: str, prompt: str) -> Generation:
        """Return the recorded generation for a request.

        Args:
            system: System prompt.
            prompt: User prompt.

        Returns:
            The recorded :class:`Generation`.

        Raises:
            CassetteMissError: If nothing is recorded for this exact request.
        """
        key = cassette_key(model=self.model, system=system, prompt=prompt)
        path = self.cassette_dir / f"{key}.json"
        if not path.is_file():
            raise CassetteMissError(
                f"no cassette for key {key}. Either this question was never recorded, "
                f"or the prompt or schema changed and every key moved with it. "
                f"Re-record with `make cassettes`; do not add a network call."
            )

        payload = _load(path)
        if payload.get("version") != CASSETTE_VERSION:
            raise CassetteMissError(
                f"cassette {key} is version {payload.get('version')!r}, "
                f"expected {CASSETTE_VERSION}"
            )
        return Generation(
            sql=payload["sql"],
            key=key,
            question=payload.get("question", ""),
            notes=payload.get("notes", ""),
        )

    def keys(self) -> list[str]:
        """Return every recorded key, sorted. Used by the consistency test."""
        return sorted(path.stem for path in self.cassette_dir.glob("*.json"))


@lru_cache(maxsize=512)
def _load(path: Path) -> dict:
    """Read and parse one cassette.

    Cached by path: the security suite is parametrised over an 18-case corpus and reads
    the same handful of files repeatedly. The cache is keyed on the path alone, which is
    safe only because cassettes are immutable fixtures -- if they ever become writable
    at runtime, this has to go.
    """
    return json.loads(path.read_text(encoding="utf-8"))
