"""ragqa: answering questions from an internal knowledge base, or declining to.

A question is matched against a corpus of policy documents, the closest passages are
screened and assembled into a prompt, a model answers from them, and every citation it
gives is checked against what it was actually shown. When the corpus has no basis for an
answer, the system says so instead of producing one.

Three things are worth knowing before changing anything:

**The most valuable thing here is the refusal.** A fluent wrong answer about notice
periods is acted on, and nothing about it looks wrong. :mod:`ragqa.rag.router` decides,
before the model is called at all, whether the retrieved passages are a basis for an
answer -- and it needs two independent signals to agree, because either alone has a
measured failure mode.

**The corpus is not trusted input.** Anyone who can edit a page can address a sentence to
the model rather than to the reader. :mod:`ragqa.rag.guardrails` withholds passages from
any document carrying instruction-shaped text, by document rather than by passage.

**There is no live model and no network call.** Answers are recorded in
``fixtures/llm_cassettes/`` and keyed by question, which is what lets a retrieval change
produce a measurably worse answer rather than a cache miss. ``ARCHITECTURE.md`` explains
why that keying was chosen and what it costs.
"""

from __future__ import annotations

__version__ = "0.5.0"

__all__ = ["__version__"]
