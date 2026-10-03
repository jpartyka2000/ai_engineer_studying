"""The index, and finding passages in it.

A pure-Python vector store. There is no database behind this and no approximate-nearest-
neighbour structure: the corpus is a few hundred chunks, a linear scan is microseconds,
and an exact scan means a retrieval test measures retrieval rather than the recall of an
index built from a seed nobody controls.

**Two scores come back for every hit, not one.**

``score``
    Cosine similarity in the hashed vector space. Good at ranking, and -- because two
    unrelated terms can share a dimension -- capable of inventing similarity out of
    nothing for a question the corpus cannot answer.

``coverage``
    The IDF-weighted fraction of the question's own terms that **literally appear** in
    the chunk. Collision-free by construction, because it compares strings rather than
    hashes. Measured on this corpus, out-of-corpus questions score 0.000 coverage where
    they reached 0.181 cosine.

The router needs both, and :mod:`ragqa.rag.router` explains why neither alone is enough.
"""

from __future__ import annotations

from dataclasses import dataclass

from ragqa.rag.chunker import Chunk, chunk_corpus
from ragqa.rag.embedding import Vectorizer, cosine_similarity, tokenize

#: Passages returned by default. Enough that the answer is usually present, few enough
#: that the prompt stays small and a wrong one is visible in a citation list.
DEFAULT_TOP_K = 4


@dataclass(frozen=True)
class Retrieved:
    """One search hit.

    Attributes:
        chunk: The passage.
        score: Cosine similarity to the query, in ``[-1, 1]``.
        coverage: IDF-weighted fraction of the query's terms present verbatim in the
            chunk, in ``[0, 1]``.
    """

    chunk: Chunk
    score: float
    coverage: float


class Index:
    """An in-memory vector index over a chunked corpus.

    Args:
        chunks: The passages to index.
        vectorizer: A vectoriser already fitted on those passages.
        vectors: Their embeddings, parallel to ``chunks``.
    """

    def __init__(
        self,
        chunks: list[Chunk],
        vectorizer: Vectorizer,
        vectors: list[list[float]],
    ) -> None:
        self.chunks = chunks
        self.vectorizer = vectorizer
        self.vectors = vectors
        self._by_id = {chunk.chunk_id: chunk for chunk in chunks}

    @classmethod
    def build(cls, documents: list[dict], **chunk_kwargs) -> Index:
        """Chunk, fit and embed a corpus in one pass.

        The vectoriser is fitted on **the chunks**, not the documents, because chunks are
        what gets retrieved -- fitting on documents would make a term appearing once per
        document look rarer than it is at the granularity that matters.

        Args:
            documents: Dicts with ``id``, ``title`` and ``text``.
            **chunk_kwargs: Passed to the chunker.

        Returns:
            A built :class:`Index`.

        Raises:
            ValueError: If the corpus yields no chunks.
        """
        chunks = chunk_corpus(documents, **chunk_kwargs)
        if not chunks:
            raise ValueError("corpus produced no chunks")
        texts = [chunk.text for chunk in chunks]
        vectorizer = Vectorizer.fit(texts)
        return cls(chunks, vectorizer, vectorizer.transform_all(texts))

    @property
    def tainted_documents(self) -> frozenset[str]:
        """Document ids with instruction-shaped text anywhere in them.

        Computed over the **whole document**, not per chunk, and that distinction is the
        point. Chunking splits a page into passages, and an injected instruction lands in
        one of them while the text it is trying to influence sits in another. Screening
        chunk by chunk would withhold the sentence carrying the attack and serve the rest
        of the page it came from -- which is all the attacker needed.

        A page somebody has tampered with is not trustworthy in its other paragraphs
        either: whoever wrote the injection had edit access to all of it.
        """
        from ragqa.rag import guardrails

        return frozenset(
            chunk.doc_id for chunk in self.chunks if guardrails.scan(chunk.text)
        )

    def __len__(self) -> int:
        """Number of indexed chunks."""
        return len(self.chunks)

    def get(self, chunk_id: str) -> Chunk | None:
        """Return a chunk by id, or ``None``."""
        return self._by_id.get(chunk_id)

    def coverage(self, query: str, chunk: Chunk) -> float:
        """Return the IDF-weighted fraction of the query's terms present in a chunk.

        Weighted rather than counted: a question matching only "the days" has covered
        nothing useful, while one matching only "probation" has covered the thing that
        made it a question. Weighting by IDF says so.

        Args:
            query: The question.
            chunk: A candidate passage.

        Returns:
            A value in ``[0, 1]``. Zero for a question with no content words.
        """
        wanted = set(tokenize(query))
        if not wanted:
            return 0.0
        present = set(tokenize(chunk.text))
        total = sum(self.vectorizer.weight(token) for token in wanted)
        if total == 0.0:
            return 0.0
        found = sum(self.vectorizer.weight(token) for token in wanted if token in present)
        return found / total

    def search(self, query: str, *, top_k: int = DEFAULT_TOP_K) -> list[Retrieved]:
        """Return the ``top_k`` closest passages, best first.

        Ties are broken by ``chunk_id`` so the order is total and reproducible. Without
        that, two equally-scoring chunks could swap between runs and a citation test
        would flake for no reason.

        Args:
            query: The question.
            top_k: How many passages to return.

        Returns:
            Hits in descending score order.

        Raises:
            ValueError: If ``top_k`` is not positive.
        """
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")

        query_vector = self.vectorizer.transform(query)
        scored = [
            (cosine_similarity(query_vector, vector), chunk)
            for chunk, vector in zip(self.chunks, self.vectors, strict=True)
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1].chunk_id))
        return [
            Retrieved(chunk=chunk, score=score, coverage=self.coverage(query, chunk))
            for score, chunk in scored[:top_k]
        ]
