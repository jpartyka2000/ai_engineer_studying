"""Splitting documents into retrievable chunks.

Two decisions, and the second one is the one people get wrong.

**Split on sentences, not on characters.** A character window cuts mid-word and mid-number
-- "notice period is 3" and "0 days" become different chunks, and neither answers the
question. Sentences are the smallest unit that still means something on its own.

**Chunks overlap.** Without overlap, a fact stated across a sentence boundary is in no
single chunk: the question matches the first half, the chunk retrieved contains the first
half, and the answer is in the chunk nobody fetched. Overlap costs index size and buys
the property that **any single sentence, together with its neighbour, appears intact in
at least one chunk**. :data:`OVERLAP_SENTENCES` is what makes that true, and
``tests/test_chunker.py`` asserts it directly rather than trusting it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Sentences per chunk. Large enough to carry a fact and its qualifier, small enough that
#: a chunk is mostly about one thing.
CHUNK_SENTENCES = 3

#: Sentences each chunk repeats from the one before. Must be at least 1, or a fact
#: spanning a boundary is unretrievable; see the module docstring.
OVERLAP_SENTENCES = 1

#: Sentence terminators followed by whitespace. Deliberately simple -- the corpus is
#: written prose, not legal text with abbreviations, and a cleverer splitter would be
#: untestable for no gain here.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    """One retrievable passage.

    Attributes:
        chunk_id: Stable identifier, ``<doc_id>#<index>``. Stable matters: it is what a
            citation refers to, so it must not move when an unrelated document is added.
        doc_id: The document this came from.
        title: The document's title, carried so a citation can be rendered without a
            second lookup.
        text: The passage itself.
        index: Position within the document, from zero.
    """

    chunk_id: str
    doc_id: str
    title: str
    text: str
    index: int


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, dropping empties.

    Args:
        text: Raw document text.

    Returns:
        Sentences with surrounding whitespace removed.
    """
    return [sentence.strip() for sentence in _SENTENCE_END.split(text.strip()) if sentence.strip()]


def chunk_document(
    doc_id: str,
    title: str,
    text: str,
    *,
    size: int = CHUNK_SENTENCES,
    overlap: int = OVERLAP_SENTENCES,
) -> list[Chunk]:
    """Split one document into overlapping chunks.

    Args:
        doc_id: Document identifier.
        title: Document title.
        text: Document body.
        size: Sentences per chunk.
        overlap: Sentences repeated from the previous chunk.

    Returns:
        Chunks in document order. A document shorter than ``size`` yields one chunk.

    Raises:
        ValueError: If ``overlap`` is not smaller than ``size``, which would make the
            window fail to advance and loop forever.
    """
    if overlap >= size:
        raise ValueError(f"overlap ({overlap}) must be smaller than size ({size})")
    if overlap < 0 or size < 1:
        raise ValueError(f"invalid chunking parameters: size={size}, overlap={overlap}")

    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: list[Chunk] = []
    step = size - overlap
    start = 0
    while start < len(sentences):
        window = sentences[start : start + size]
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}#{len(chunks)}",
                doc_id=doc_id,
                title=title,
                text=" ".join(window),
                index=len(chunks),
            )
        )
        if start + size >= len(sentences):
            break
        start += step
    return chunks


def chunk_corpus(documents: list[dict], **kwargs) -> list[Chunk]:
    """Chunk every document in a corpus.

    Args:
        documents: Dicts with ``id``, ``title`` and ``text``.
        **kwargs: Passed to :func:`chunk_document`.

    Returns:
        Every chunk, in corpus order.
    """
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(
            chunk_document(document["id"], document["title"], document["text"], **kwargs)
        )
    return chunks
