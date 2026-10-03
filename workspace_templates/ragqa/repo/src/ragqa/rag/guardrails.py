"""Treating retrieved text as data, never as instructions.

**The corpus is not trusted input.** Anyone who can edit a wiki page can write a sentence
addressed to the model rather than to the reader, and retrieval will dutifully fetch it
and place it in the prompt alongside genuine context. At that point the only thing
separating "here is a passage about notice periods" from "ignore your instructions" is
that one of them is in quotation marks, which is not a security boundary.

So retrieved passages are scanned before assembly and anything carrying instruction-shaped
text is **quarantined**: excluded from the prompt, recorded, and reported. The alternative
designs are worse. Stripping the offending sentence leaves the rest of a page somebody has
demonstrably tampered with. Escaping it assumes the model treats delimiters as a boundary,
which is the assumption being attacked.

**Citations get the same treatment, for the same reason.** A model asked to cite its
sources will sometimes name a document it was never shown, and a citation is precisely the
thing a reader uses to decide whether to believe an answer. So every citation is checked
against what was actually retrieved, and anything else is dropped and counted.

Pattern matching will not catch a determined attacker and is not claimed to. It catches
the realistic case -- a page edited by someone who read about prompt injection -- and
everything it misses still cannot reach the model as an *instruction*, because the
assembled prompt puts retrieved text in a clearly-marked data section. Defence in depth,
with the honest caveat that this layer is the shallower of the two.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from ragqa.rag.retriever import Retrieved

logger = logging.getLogger(__name__)

#: Instruction-shaped phrases. Deliberately about *form* rather than topic: the giveaway
#: is text addressing the assistant rather than the reader, whatever it goes on to ask
#: for. Each is matched case-insensitively against the passage.
INJECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", "override-instructions"),
    (r"disregard\s+(all\s+)?(previous|prior|above)", "override-instructions"),
    (r"reveal\s+.{0,30}(system\s+prompt|instructions)", "exfiltrate-prompt"),
    (r"(print|repeat|output)\s+.{0,30}(system\s+prompt|instructions)", "exfiltrate-prompt"),
    (r"you\s+are\s+now\s+", "persona-override"),
    (r"pretend\s+(to\s+be|that\s+you)", "persona-override"),
)

_COMPILED = tuple((re.compile(pattern, re.IGNORECASE), label) for pattern, label in INJECTION_PATTERNS)


@dataclass(frozen=True)
class Quarantined:
    """A passage withheld from the prompt.

    Attributes:
        chunk_id: The passage's id.
        labels: Which pattern families matched.
    """

    chunk_id: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class ScreenResult:
    """The outcome of screening retrieved passages.

    Attributes:
        safe: Passages cleared for the prompt, in their original order.
        quarantined: Passages withheld, with the reasons.
    """

    safe: list[Retrieved] = field(default_factory=list)
    quarantined: list[Quarantined] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """Whether everything retrieved was cleared."""
        return not self.quarantined


def scan(text: str) -> tuple[str, ...]:
    """Return the labels of every injection pattern matching a passage.

    Args:
        text: Passage text.

    Returns:
        Matching labels, deduplicated, in declaration order.
    """
    labels: list[str] = []
    for pattern, label in _COMPILED:
        if pattern.search(text) and label not in labels:
            labels.append(label)
    return tuple(labels)


def screen(
    retrieved: list[Retrieved], *, tainted_documents: frozenset[str] = frozenset()
) -> ScreenResult:
    """Withhold any retrieved passage from a document carrying instruction-shaped text.

    Args:
        retrieved: Hits from the retriever.
        tainted_documents: Document ids known to contain an injection anywhere in them,
            from :attr:`~ragqa.rag.retriever.Index.tainted_documents`.

    Returns:
        A :class:`ScreenResult`. The order of the safe passages is preserved, because it
        is the ranking and the prompt presents them in it.

    Note:
        **Withheld by document, not by passage.** Chunking splits a page into passages,
        so an injected instruction sits in one chunk while the claim it is trying to
        influence sits in the next. Screening the passage alone drops the sentence
        carrying the attack and serves the rest of the page, which is all the attacker
        needed. The passage's own text is still scanned, so a caller that does not supply
        ``tainted_documents`` gets the weaker guarantee rather than none at all.
    """
    safe: list[Retrieved] = []
    quarantined: list[Quarantined] = []
    for hit in retrieved:
        labels = scan(hit.chunk.text)
        if not labels and hit.chunk.doc_id in tainted_documents:
            labels = ("tainted-document",)
        if labels:
            logger.warning("quarantined %s: %s", hit.chunk.chunk_id, ",".join(labels))
            quarantined.append(Quarantined(chunk_id=hit.chunk.chunk_id, labels=labels))
        else:
            safe.append(hit)
    return ScreenResult(safe=safe, quarantined=quarantined)


@dataclass(frozen=True)
class CitationCheck:
    """The outcome of validating an answer's citations.

    Attributes:
        supported: Cited ids that were actually retrieved and shown.
        fabricated: Cited ids that were not. Dropped from the response.
    """

    supported: tuple[str, ...]
    fabricated: tuple[str, ...]


def validate_citations(cited: list[str], shown: list[str]) -> CitationCheck:
    """Keep only citations naming a passage that was actually put in front of the model.

    Args:
        cited: Chunk ids the model claimed to use.
        shown: Chunk ids actually included in the prompt.

    Returns:
        A :class:`CitationCheck`.

    Note:
        Checked against what was **shown**, not against the corpus. A citation naming a
        real document the model never saw is fabricated: nothing it said about that
        document came from reading it. Validating against the corpus instead would pass
        exactly that case, which is the one worth catching.
    """
    shown_set = set(shown)
    supported = tuple(dict.fromkeys(c for c in cited if c in shown_set))
    fabricated = tuple(dict.fromkeys(c for c in cited if c not in shown_set))
    if fabricated:
        logger.warning("dropped %d fabricated citation(s): %s", len(fabricated), fabricated)
    return CitationCheck(supported=supported, fabricated=fabricated)
