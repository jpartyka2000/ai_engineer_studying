# Architecture

Why this service is shaped the way it is. Read this before changing anything under
`rag/` or `eval/`.

## The shape

```
question
   -> retrieve        closest passages, two scores each
   -> screen          withhold passages from tampered documents
   -> route           answer, or refuse without calling the model
   -> assemble        whole passages, within a budget
   -> generate        a recorded answer, with claimed citations
   -> validate        drop citations naming passages never shown
```

Every step can stop the one after it. Two orderings are load-bearing:

**Screening happens before routing.** If the only passage that ranked was a tampered one,
withholding it must leave the router with nothing, so the system refuses. Screening
afterwards would mean the router approved an answer on the strength of a passage that was
then removed.

**Routing happens before generation.** A refusal must not reach the model at all — that
is what makes it cheap, and it is why there is no recorded answer for any unanswerable
question. Reaching the model for one of them raises rather than inventing something.

## Refusing is the product

A fluent wrong answer about notice periods gets acted on, and nothing about it looks
wrong. So the most valuable thing this system does is decline, and the router is the
component that matters most.

**It requires two independent signals to agree, and the reason is measured.**

*Similarity alone does not work.* The vector space is hashed, so unrelated terms share
dimensions and manufacture similarity out of nothing. Measured on this corpus:
out-of-corpus questions reach **0.181** cosine while genuine questions go as low as
**0.148**. The distributions overlap. There is no threshold on this number that separates
"we have an answer" from "we do not" — any choice either answers nonsense or refuses real
questions. "What is the capital of Peru?" scores 0.159 against this corpus.

*Coverage alone does not work either.* It asks whether the question's own words appear in
the passage, which is collision-free but blind to ranking: a chunk can contain a rare term
in a completely unrelated sentence.

*Together they separate.* Out-of-corpus questions score **0.000** coverage. Requiring both
is what makes refusal reliable, and `ragqa eval` reports which signal caught each one.

## The embedder is a stand-in, and the numbers were measured

A hashed TF-IDF vectoriser rather than an embedding API, so the corpus can be rebuilt by
anyone with no credentials and no network, and so the tests are exactly reproducible.

The cost is semantics: passages meaning the same thing in different words are not close
here, only ones sharing vocabulary. This retriever behaves like good lexical search. Every
exercise built on it is therefore about **retrieval plumbing** rather than embedding
quality — which could not be graded anyway.

Two parameters were measured rather than chosen, against 24 benchmark questions:

| | top-1 retrieval |
|---|---|
| plain term counts, 64 dimensions | 4/6 on an early sample |
| TF-IDF, 256 dimensions | 18/23 |
| TF-IDF, 512 dimensions | 22/23 |
| **TF-IDF, 1024 dimensions** | **23/23** |

A retriever wrong a fifth of the time would make everything downstream a coin toss.

**IDF makes the vectoriser fitted, not pure.** A term's weight depends on the corpus, so
queries must be transformed by the same fitted vectoriser the index was built with.

## The model is recorded, and the key is the question

Answers live in `fixtures/llm_cassettes/`, keyed by
`sha256(model | system | question)`. A miss is an error; there is no network fallback.

**The key deliberately excludes the retrieved passages, and that is the most consequential
decision in this codebase.** The obvious design keys on everything sent to the model,
assembled prompt included. Here that would be actively harmful: the prompt embeds the
retrieved context, so *any* retrieval change — a different chunk size, a different
ranking, one fewer passage — would change the key and turn every request into a cassette
miss. A retrieval bug would present as "no recording found" rather than as a worse answer,
which is useless for diagnosis and wrong about what retrieval bugs actually do.

Keying on the question means the recorded answer is **what the model says when retrieval
is working**. The honest consequence: this service cannot measure whether bad context
produces a bad answer, because the answer is fixed. What it measures instead is everything
the answer is built on — whether the right passages were found, whether the citations are
supported, and whether the system knew to refuse. Those are functions of the retrieved set.

A practical benefit falls out: editing the corpus does not invalidate a single cassette.

## Chunking, and the fact that would otherwise be unretrievable

Passages are three sentences with one sentence of overlap. The overlap costs index size
and buys one property: **any two adjacent sentences appear together in at least one
chunk**.

Without it, a fact stated across a sentence boundary belongs to no chunk at all. The
question matches the half it can see, the chunk retrieved contains that half, and the
other half is somewhere nobody fetched — so the fact is not ranked poorly, it is
unretrievable at any `top_k`. `hr-leave` is written to have exactly this shape, and
`tests/test_chunker.py` asserts the property across the whole corpus.

## Trimming drops whole passages, never halves of them

Passages vary in length by a factor of eight here, so a budget is in characters rather
than passages. When it is exceeded the lowest-ranked passage is removed entirely.

Truncating mid-passage is the tempting alternative and it quietly breaks the thing this
system is judged on: the passage is still labelled and still citable, so the answer cites
an id whose text the model only partly saw. The citation validates, the audit trail looks
clean, and the grounding is gone.

## The corpus is not trusted input

Anyone who can edit a wiki page can write a sentence addressed to the model rather than to
the reader. `eng-handbook-draft` is such a page, and it is not a contrived case — it
**outranks the genuine on-call document** for "What is the on-call allowance?", because it
is also genuinely about that topic.

**Quarantine is by document, not by passage.** Chunking splits a page into passages, so an
injected instruction lands in one and the claim it is trying to influence lands in another.
Screening passage by passage withholds the sentence carrying the attack and serves the rest
of the page — which is all the attacker needed. A page somebody has tampered with is not
trustworthy in its other paragraphs either.

Pattern matching will not stop a determined attacker and is not claimed to. It catches the
realistic case, and the prompt puts retrieved text in a clearly-marked data section as a
second, shallower layer.

## The four metrics, and how each can be fooled

Each is a pure function over strings and ids — no model, no database, no corpus — which is
what lets every one be tested against a constant worked out by hand.

**Exact match** is normalised, so punctuation and articles do not decide it.

**Token F1** is the harmonic mean of precision and recall. Recall alone would reward
padding: an answer reciting the whole handbook contains every gold token and would score
1.0. Measured, a padded answer scores **0.435** where recall says 1.0.

**Citation precision** is measured against what was actually **retrieved and shown**, not
against the corpus. A citation naming a real document the model never read is fabricated —
nothing it said about that document came from reading it. Checking against the corpus
would score exactly that case as correct.

**Refusal correctness** is reported as **balanced accuracy**, never plain accuracy. The
evaluation set holds 27 answerable questions and 7 unanswerable ones, as any real one
would. A system that simply answers everything scores **0.794** on plain accuracy and
**0.500** on balanced — and the second is the truth about the behaviour being measured.

The baseline is 1.0 on all four. That is deliberate: it makes every one a regression test
with nothing to argue about.

## What is deliberately not here

**No vector database.** A few hundred chunks scanned linearly is microseconds, and an
exact scan means a retrieval test measures retrieval rather than the recall of an
approximate index built from a seed nobody controls.

**No numpy.** Every number here is arithmetic that can be checked by hand.

**No LLM SDK.** See above. This service makes no network calls at all.

**No conversation memory in the answer path.** Each question is retrieved and answered on
its own. History is stored for operators and for harvesting evaluation questions, not fed
back into the next answer — which would make every bug depend on what was asked before it.
