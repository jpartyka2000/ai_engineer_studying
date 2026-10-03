"""Turning text into a vector, deterministically and without a model.

**This stands in for an offline embedding job.** A real deployment calls an embedding API
and stores the results; doing that here would make the corpus un-rebuildable without a
key, the tests non-deterministic, and the whole exercise dependent on a vendor being up.
Instead this is a hashed TF-IDF vectoriser: a token is mapped to a dimension and a sign
by its SHA-256, weighted by how rare it is in the corpus, and accumulated.

What that buys and what it costs, stated plainly:

**It buys** exact reproducibility -- the same corpus yields the same vectors on every
machine forever -- and an index anyone can rebuild with no credentials and no network.

**It costs** semantics. Two passages meaning the same thing in different words are not
close in this space; only shared vocabulary brings them together. So this retriever
behaves like good lexical search rather than a semantic one. Every exercise built on it is
about **retrieval plumbing** -- weighting, normalisation, chunking, thresholds, ranking,
citation handling -- and never about embedding quality, which could not be graded anyway.

**Why IDF, and why 1024 dimensions.** Both were measured on this corpus, not chosen.
Plain term counts weight "days" -- which appears in half the handbook -- the same as
"probation", and the common term wins every vector it touches; IDF fixes that. Dimension
count then fixes what is left, which is hash collisions: against the 23 benchmark
questions, top-1 retrieval is 18/23 at 256 dimensions, 22/23 at 512 and **23/23 at
1024**, with a vocabulary of 469 terms. A retriever that is wrong a fifth of the time
would make every exercise built on it a coin toss, so this is load-bearing rather than
tuning.

**Collisions do not disappear, they go quiet -- which is why the router does not trust
this score alone.** Two unrelated terms sharing a dimension produce similarity out of
nothing, and measured against out-of-corpus questions the effect is large enough to
matter: their top scores reach 0.181 while genuine questions go as low as 0.148, so no
threshold on cosine alone separates "we have an answer" from "we do not". See
:mod:`ragqa.rag.router`, which pairs this score with a collision-free lexical check.

**The consequence of IDF: this vectoriser is fitted, not pure.** A term's weight depends
on the corpus, so queries must be transformed by the *same* fitted vectoriser the index
was built with. Transforming a query with an unfitted one silently gives every term the
weight of a rare term, which is a different and much worse ranking.

**Vectors are unnormalised.** Normalisation happens at compare time in
:func:`cosine_similarity`, because the reranker wants the raw magnitudes too.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

#: Dimensionality. See the module docstring: measured, not chosen.
DIMENSIONS = 1024

#: Tokens below this length carry no retrieval signal and inflate every vector's norm.
MIN_TOKEN_LENGTH = 2

#: Words so common they match everything. Kept deliberately short: an aggressive stop
#: list silently removes the distinguishing term from somebody's question.
STOP_WORDS = frozenset(
    """
    a an and are as at be by for from has have how in is it its of on or that the
    this to was were what when where which who why will with you your
    """.split()
)

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Split text into the tokens the vectoriser sees.

    Lower-cased, alphanumeric runs only, short tokens and stop words dropped. Shared by
    the vectoriser and the token-F1 metric, so "what counts as a word" has exactly one
    definition in this codebase and a scoring change cannot silently diverge from a
    retrieval change.

    Args:
        text: Raw text.

    Returns:
        Tokens in order, duplicates preserved -- term frequency is signal.
    """
    return [
        token
        for token in _TOKEN.findall(text.lower())
        if len(token) >= MIN_TOKEN_LENGTH and token not in STOP_WORDS
    ]


def _feature(token: str, dimensions: int) -> tuple[int, float]:
    """Map a token to a dimension and a sign.

    The sign comes from a different byte of the digest than the dimension, so two tokens
    colliding in one dimension are as likely to cancel as to reinforce. Without it every
    vector would be non-negative and every pair of documents would look alike.
    """
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    dimension = int.from_bytes(digest[:4], "big") % dimensions
    sign = 1.0 if digest[4] & 1 else -1.0
    return dimension, sign


@dataclass
class Vectorizer:
    """A hashed TF-IDF vectoriser, fitted on a corpus.

    Attributes:
        dimensions: Size of the output vector.
        idf: Token -> inverse document frequency, learned by :meth:`fit`.
        unseen_idf: Weight for a token absent from the corpus. A query term nobody has
            written about is maximally rare, so it gets the largest weight -- which is
            right: it is the most discriminating thing the asker said.
    """

    dimensions: int = DIMENSIONS
    idf: dict[str, float] = field(default_factory=dict)
    unseen_idf: float = 0.0

    @classmethod
    def fit(cls, texts: Iterable[str], *, dimensions: int = DIMENSIONS) -> Vectorizer:
        """Learn inverse document frequencies from a corpus.

        Args:
            texts: The chunk texts the index will hold.
            dimensions: Output dimensionality.

        Returns:
            A fitted :class:`Vectorizer`.

        Raises:
            ValueError: If the corpus is empty. Fitting on nothing yields a vectoriser
                that weights every term identically, which is a silently bad index.
        """
        document_frequency: dict[str, int] = {}
        total = 0
        for text in texts:
            total += 1
            for token in set(tokenize(text)):
                document_frequency[token] = document_frequency.get(token, 0) + 1

        if total == 0:
            raise ValueError("cannot fit a vectoriser on an empty corpus")

        # Smoothed, so a term in every document still has a small positive weight rather
        # than exactly zero -- a term that appears everywhere is weak evidence, not an
        # error to be divided away.
        idf = {
            token: math.log((total + 1) / (count + 0.5))
            for token, count in document_frequency.items()
        }
        return cls(
            dimensions=dimensions,
            idf=idf,
            unseen_idf=math.log((total + 1) / 0.5),
        )

    @property
    def fitted(self) -> bool:
        """Whether this vectoriser has learned any weights."""
        return bool(self.idf)

    def weight(self, token: str) -> float:
        """Return a token's IDF weight, treating unknown tokens as maximally rare."""
        return self.idf.get(token, self.unseen_idf)

    def transform(self, text: str) -> list[float]:
        """Embed text into an unnormalised vector.

        Args:
            text: Raw text.

        Returns:
            A vector of length :attr:`dimensions`.

        Raises:
            RuntimeError: If the vectoriser has not been fitted. Transforming with an
                unfitted vectoriser gives every term the same weight, which produces a
                plausible-looking vector and a quietly wrong ranking -- so it raises
                rather than guessing.
        """
        if not self.fitted:
            raise RuntimeError(
                "vectoriser is not fitted; transform would weight every term identically"
            )
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            dimension, sign = _feature(token, self.dimensions)
            vector[dimension] += sign * self.weight(token)
        return vector

    def transform_all(self, texts: Iterable[str]) -> list[list[float]]:
        """Embed many texts, in order."""
        return [self.transform(text) for text in texts]


def norm(vector: Sequence[float]) -> float:
    """Return the Euclidean norm of a vector."""
    return math.sqrt(sum(value * value for value in vector))


def dot(left: Sequence[float], right: Sequence[float]) -> float:
    """Return the dot product of two equal-length vectors.

    Raises:
        ValueError: If the lengths differ, which means something was embedded by a
            different vectoriser and the index needs rebuilding.
    """
    if len(left) != len(right):
        raise ValueError(f"dimension mismatch: {len(left)} vs {len(right)}")
    return sum(a * b for a, b in zip(left, right, strict=True))


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return the cosine similarity of two vectors, in ``[-1, 1]``.

    **Not a dot product.** These vectors are unnormalised, so magnitude grows with the
    amount of text. Ranking by dot product therefore ranks partly by length: a long chunk
    mentioning the query term once can outscore a short chunk that is entirely about it.
    Dividing by both norms makes the comparison about direction, which is what "similar"
    is supposed to mean.

    Args:
        left: First vector.
        right: Second vector.

    Returns:
        The similarity, or 0.0 if either vector is all zeros -- which happens for text
        made only of stop words, and is a real input rather than an edge case.
    """
    left_norm = norm(left)
    right_norm = norm(right)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot(left, right) / (left_norm * right_norm)
