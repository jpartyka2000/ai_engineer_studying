"""Chunking, and the one property that makes overlap worth its cost.

Overlap doubles part of the index for a reason that is invisible until it is missing: a
fact stated across two adjacent sentences belongs to **no chunk at all** if the window
boundary happens to fall between them. The question matches the half it can see, the
chunk retrieved contains that half, and the other half is in a chunk nobody fetched.

``test_a_fact_spanning_a_boundary_survives_in_one_chunk`` pins that directly against a
document written to have exactly this shape. It is a binary property -- either some chunk
contains both sentences or none does -- which is a far better test than watching an
average retrieval score move by a point or two.
"""

from __future__ import annotations

import pytest

from ragqa.rag.chunker import (
    CHUNK_SENTENCES,
    OVERLAP_SENTENCES,
    chunk_corpus,
    chunk_document,
    split_sentences,
)
from tests.conftest import question_by_id

#: The two halves of the rule in hr-leave that straddle a chunk boundary.
FIRST_HALF = "at least two weeks in advance"
SECOND_HALF = "more than ten consecutive days"


def test_sentences_split_on_terminators() -> None:
    text = "One. Two! Three? Four."
    assert split_sentences(text) == ["One.", "Two!", "Three?", "Four."]


def test_empty_text_yields_no_chunks() -> None:
    assert chunk_document("d", "T", "   ") == []


def test_a_short_document_is_one_chunk() -> None:
    """Two sentences, window of three: one chunk, and the loop must still terminate."""
    chunks = chunk_document("d", "T", "One sentence. Two sentences.")
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "d#0"


def test_chunk_ids_match_their_position() -> None:
    """``<doc_id>#<index>`` with the index counting from zero.

    A citation is an id, so an id that does not match its own position means a citation
    resolves to the neighbouring passage -- an answer that looks sourced and is not.
    """
    text = " ".join(f"Sentence {n}." for n in range(1, 10))
    chunks = chunk_document("doc", "T", text)
    for position, chunk in enumerate(chunks):
        assert chunk.index == position
        assert chunk.chunk_id == f"doc#{position}"


def test_consecutive_chunks_share_their_overlap() -> None:
    """With size 3 and overlap 1, chunk N ends with the sentence chunk N+1 starts with."""
    text = " ".join(f"S{n}." for n in range(1, 10))
    chunks = chunk_document("d", "T", text)
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert earlier.text.split()[-1] == later.text.split()[0]


def test_a_fact_spanning_a_boundary_survives_in_one_chunk(documents) -> None:
    """**The property overlap exists for.**

    ``hr-leave`` states the notice requirement in one sentence and the exception for long
    requests in the next. A question about booking a two-week holiday needs both.

    With overlap, exactly one chunk contains both. Without it, the window boundary falls
    between them and **no chunk contains both** -- so the fact is not merely ranked
    poorly, it is unretrievable at any ``top_k``.
    """
    leave = next(doc for doc in documents if doc["id"] == "hr-leave")

    with_overlap = chunk_document(leave["id"], leave["title"], leave["text"])
    holding_both = [
        chunk for chunk in with_overlap if FIRST_HALF in chunk.text and SECOND_HALF in chunk.text
    ]
    assert holding_both, "no chunk contains both halves of the rule"

    without_overlap = chunk_document(
        leave["id"], leave["title"], leave["text"], overlap=0
    )
    assert not [
        chunk
        for chunk in without_overlap
        if FIRST_HALF in chunk.text and SECOND_HALF in chunk.text
    ], "this document was written so that removing overlap splits the rule; it no longer does"


def test_every_adjacent_sentence_pair_appears_together_somewhere(documents) -> None:
    """The general form of the property above, over the whole corpus.

    For every document, every pair of neighbouring sentences must appear together in at
    least one chunk. That is the guarantee overlap buys, and it either holds for all of
    them or the chunker has a gap somewhere nobody has looked.
    """
    for document in documents:
        sentences = split_sentences(document["text"])
        chunks = chunk_document(document["id"], document["title"], document["text"])
        for earlier, later in zip(sentences, sentences[1:], strict=False):
            assert any(
                earlier in chunk.text and later in chunk.text for chunk in chunks
            ), f"{document['id']}: no chunk holds both {earlier[:30]!r} and {later[:30]!r}"


def test_overlap_must_be_smaller_than_the_window() -> None:
    """Otherwise the window never advances and the loop does not terminate."""
    with pytest.raises(ValueError, match="smaller than"):
        chunk_document("d", "T", "One. Two. Three.", size=2, overlap=2)


def test_the_defaults_are_the_documented_ones() -> None:
    """Pinned because the corpus was written against them and several tests assume them."""
    assert (CHUNK_SENTENCES, OVERLAP_SENTENCES) == (3, 1)


def test_chunking_the_corpus_preserves_document_order(documents) -> None:
    chunks = chunk_corpus(documents)
    first_seen = []
    for chunk in chunks:
        if chunk.doc_id not in first_seen:
            first_seen.append(chunk.doc_id)
    assert first_seen == [doc["id"] for doc in documents]
