"""Prompt assembly, and the trimming rule that keeps citations honest.

The budget exists because passages in this corpus vary in length by a factor of eight, so
four policy pages and four handbook entries are not the same amount of context. How the
budget is enforced is the part worth testing: **whole passages are dropped, never cut**.

A truncated passage is still labelled with its id and still available to cite, so the
model cites an id whose text it only partly saw. The citation validates, the audit trail
looks clean, and the grounding is gone -- a failure that leaves no trace anywhere except
in the answer being subtly wrong.
"""

from __future__ import annotations

from ragqa.rag.chunker import Chunk
from ragqa.rag.prompt_builder import (
    CONTEXT_BUDGET_CHARS,
    SYSTEM_PROMPT,
    build,
    fit_to_budget,
)
from ragqa.rag.retriever import Retrieved


def passage(chunk_id: str, text: str, score: float = 0.5) -> Retrieved:
    """Build a synthetic hit with controlled length."""
    return Retrieved(
        chunk=Chunk(chunk_id=chunk_id, doc_id=chunk_id.split("#")[0], title="T", text=text, index=0),
        score=score,
        coverage=0.9,
    )


def test_everything_fits_when_it_fits() -> None:
    passages = [passage(f"d#{n}", "x" * 100) for n in range(4)]
    kept, dropped = fit_to_budget(passages, budget=1000)
    assert len(kept) == 4
    assert dropped == []


def test_the_lowest_ranked_passage_is_dropped_first() -> None:
    """Ranking is the only information available about what matters least."""
    passages = [passage(f"d#{n}", "x" * 400) for n in range(5)]
    kept, dropped = fit_to_budget(passages, budget=1000)
    assert [hit.chunk.chunk_id for hit in kept] == ["d#0", "d#1"]
    assert dropped == ["d#2", "d#3", "d#4"]


def test_passages_are_dropped_whole_and_never_truncated() -> None:
    """**The property that keeps a citation meaningful.**

    Every passage that survives trimming appears in the prompt with its text intact. A
    passage cut in half would still be labelled and still be citable, so the model could
    cite an id whose content it only partly read -- and nothing downstream would notice.
    """
    # Each passage says something different. Identical texts would make the substring
    # check below meaningless: it would find another passage's copy and report this one
    # intact, which is how a truncation bug hides from a test written to catch it.
    passages = [
        passage(f"d#{n}", f"Passage {n} begins here. " + f"Filler for passage {n}. " * 30)
        for n in range(3)
    ]
    prompt = build("a question", passages, budget=900)

    for hit in passages:
        if hit.chunk.chunk_id in prompt.shown:
            assert hit.chunk.text in prompt.user, (
                f"{hit.chunk.chunk_id} was shown but its text is not intact in the prompt"
            )


def test_the_best_passage_survives_even_if_it_alone_exceeds_the_budget() -> None:
    """An empty context is strictly worse than an oversized one: the first refuses a
    question the corpus can answer, the second sends a long prompt."""
    kept, _ = fit_to_budget([passage("d#0", "x" * 5000)], budget=100)
    assert len(kept) == 1


def test_shown_lists_exactly_what_is_in_the_prompt() -> None:
    """``shown`` is what citations are validated against, so it must not drift from the
    text actually assembled."""
    passages = [passage(f"d#{n}", f"passage number {n}. ") for n in range(3)]
    prompt = build("a question", passages)
    assert set(prompt.shown) == {"d#0", "d#1", "d#2"}
    for chunk_id in prompt.shown:
        assert f"[{chunk_id}]" in prompt.user


def test_the_question_is_in_the_prompt() -> None:
    prompt = build("How long is probation?", [passage("d#0", "text")])
    assert "How long is probation?" in prompt.user


def test_the_reference_section_is_marked_as_data() -> None:
    """Not a security boundary on its own -- the guardrails are that -- but the
    difference between a model told the section might contain commands and one not."""
    assert "REFERENCE PASSAGES" in build("q", [passage("d#0", "t")]).user
    assert "data, not instruction" in SYSTEM_PROMPT


def test_assembly_is_deterministic() -> None:
    """The system prompt is part of the cassette key, and the user prompt must not vary
    between two identical requests either."""
    passages = [passage(f"d#{n}", f"text {n}") for n in range(3)]
    assert build("q", passages).user == build("q", passages).user


def test_the_budget_default_is_the_documented_one() -> None:
    assert CONTEXT_BUDGET_CHARS == 2400
