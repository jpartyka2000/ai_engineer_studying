"""Exercises built on the ``ragqa`` base application.

Same ``(base_app, mutations)`` shape as the other catalog modules, and baselines are
likewise **measured** into ``baselines.json`` by the verification harness rather than
authored here.

What distinguishes this base app is that **the system keeps answering**. Nothing here
throws, nothing returns an empty page, and the prose that comes back is as fluent after
the defect as before it. What changes is whether the answer was grounded in the right
passage, whether the citations under it mean anything, and whether the system knew to
say it did not know. A retrieval-augmented assistant fails by being confidently wrong,
and every brief here opens the way that is actually noticed: somebody reads an answer and
recognises that it is about the wrong thing.

**The three evaluation-framework exercises are different in kind** and the briefs say so.
A loosened metric cannot show on a system that is already answering correctly, so under
all three of them every end-to-end number stays at 1.0 and the benchmark looks healthy.
That is exactly why metric bugs survive in real projects for years, and it is why those
three are caught by unit tests over hand-computed inputs rather than by the benchmark.
A candidate who notices that the headline numbers did not move -- and understands why
that is the point rather than a contradiction -- has found the lesson.
"""

import json
from pathlib import Path
from typing import Any

from apps.workspace.enums import BaseApp, CheckKind, Database, Difficulty, ExerciseType

_BASELINES: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "baselines.json").read_text(encoding="utf-8")
)


def baseline(slug: str) -> dict[str, Any]:
    """Return the measured pre-fix baseline for an exercise.

    Args:
        slug: The exercise slug.

    Returns:
        A dict with ``failing_nodes``, ``passing_nodes`` and ``metrics``.

    Raises:
        KeyError: If no baseline has been measured, which should fail the seed command
            rather than silently ship an ungradeable exercise.
    """
    data = _BASELINES[slug]
    return {
        "failing_nodes": data["failing_nodes"],
        "passing_nodes": data["passing_nodes"],
        "metrics": data.get("metrics", {}),
    }


#: The tests are the proof, so editing them is tampering. Three additions specific to
#: this base app: ``corpus/**`` because the knowledge base is what every retrieval
#: assertion is measured against, ``eval/**`` because the labelled set is the definition
#: of correct, and ``fixtures/**`` because the recordings are what make any of it
#: reproducible. Rewriting any of the three would move the constants rather than fix the
#: code.
STANDARD_PROTECTED = [
    "tests/**",
    "pyproject.toml",
    "ci/run_ci.sh",
    ".github/workflows/ci.yml",
    "corpus/**",
    "eval/**",
    "fixtures/**",
    "tools/gen_cassettes.py",
]

#: Shared context: why the router needs two signals, with the measurements.
TWO_SIGNALS_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "29-50",
    "why": (
        "'Refusing is the product'. Gives the measured overlap that makes a single "
        "threshold unworkable -- out-of-corpus questions reach 0.181 cosine while real "
        "ones drop to 0.148 -- and why the second, collision-free signal exists."
    ),
}

#: Shared context: what the cassette key does and does not include.
RECORDED_MODEL_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "75-95",
    "why": (
        "'The model is recorded, and the key is the question'. Explains why editing the "
        "corpus or changing retrieval does not invalidate a cassette, and states plainly "
        "what this service can and cannot measure as a result."
    ),
}

#: Shared context: the four metrics and the way each can be fooled.
METRICS_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "135-158",
    "why": (
        "'The four metrics, and how each can be fooled'. Each one is paired with the "
        "specific wrong implementation it is defined against, with the numbers."
    ),
}


# ---------------------------------------------------------------------------
# ex-042 -- genAI QA chatbot
# ---------------------------------------------------------------------------

EX042 = {
    "slug": "ex-042-long-policy-pages-outrank-the-right-answer",
    "exercise_number": 42,
    "title": "Short handbook entries stopped winning against long policy pages",
    "exercise_type": ExerciseType.GENAI_CHATBOT,
    "base_app": BaseApp.RAGQA,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "ranking_biased_by_passage_length",
    "time_limit_minutes": 40,
    "expected_time_minutes": 24,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["rag", "retrieval", "ranking", "vectors", "python"],
    "brief_md": """\
## SUP-914 — the assistant answers with the wrong document

**Reported by:** the people team
**Severity:** SEV-3, but it is eroding trust quickly

Somebody asked the assistant what the data classification levels are. It replied with
something from the **supplier management policy**. Several other questions have come back
with one of the long policy pages instead of the short handbook entry that actually
answers them.

The answers are fluent and they cite a real document. They are simply about the wrong
thing, which is harder to notice than an error would be.

### What we know

- The corpus has not changed. The same questions used to work.
- `make test` is red, and one of the retrieval benchmark cases names a question that
  regressed. Read the rest of the failures too — the pattern across them is the finding.
- The long policy pages are long for a legitimate reason: they are policies. The corpus
  deliberately contains passages that differ in length by a factor of eight.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
make eval
```

`make eval` scores the system against the labelled set. A healthy build is 1.0 on every
metric, so anything less is a regression rather than a judgement call.

Try a question by hand and look at what comes back:

```bash
make ask Q="what are the data classification levels?"
```

### What we need

Ranking that is about **what a passage is about**, not about how much of it there is. And
a `NOTES.md` that explains why the long documents won — somebody will ask whether the fix
means the policy pages are now unfindable, and they should not be.
""",
    "definition_of_done": [
        "R1: every retrieval benchmark question retrieves its document",
        "R2: the evaluation set scores 1.0 on exact match",
        "R3: no answerable question is refused",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains why length was deciding the ranking",
    ],
    "focus_paths": ["src/ragqa/rag/retriever.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_retriever.py::test_the_benchmark_question_retrieves_its_document",
            "weight": 5,
            "required": True,
            "description": "All 24 benchmark questions retrieve the document that answers them",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_eval.py::test_exact_match_is_perfect",
            "weight": 3,
            "required": True,
            "description": "The labelled set is answered exactly again",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_eval.py::test_no_answerable_question_was_refused",
            "weight": 2,
            "required": True,
            "description": "Nothing the corpus can answer is being refused",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including the evaluation gate",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, corpus, evaluation set and fixtures are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained the mechanism rather than the symptom: these vectors are "
                "unnormalised, so magnitude grows with the amount of text, and ranking by "
                "dot product ranks partly by length"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Confirmed the policy pages are still retrievable for questions that are "
                "genuinely about them, rather than declaring victory on the regression"
            ),
        },
    ],
    "baseline": baseline("ex-042-long-policy-pages-outrank-the-right-answer"),
    "context_excerpts": [
        {
            "path": "src/ragqa/rag/embedding.py",
            "line_range": "1-43",
            "why": (
                "The vectoriser's module docstring, which states that vectors are stored "
                "unnormalised and that normalisation is the retriever's job at compare "
                "time. The contract the fix has to restore."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "51-74",
            "why": (
                "'The embedder is a stand-in, and the numbers were measured'. Gives the "
                "retrieval benchmark figures, so a candidate can tell a real regression "
                "from the retriever's normal limitations."
            ),
        },
    ],
    "hints": [
        "Run `make test` and read the retrieval benchmark failure. Then run "
        '`make ask Q="what are the data classification levels?"` and look at which '
        "document came back rather than only at the answer.",
        "Compare the passage that won against the one that should have. How do they "
        "differ, apart from their subject matter?",
        "`Index.search` scores each chunk against the query. Look at what it calls to do "
        "that, and read what `embedding.py` says about why that particular function "
        "exists rather than the obvious alternative.",
    ],
    "grading_notes": """\
**Root cause.** ``Index.search`` ranks with ``dot`` instead of ``cosine_similarity``.
Vectors in this codebase are stored unnormalised -- deliberately, because the magnitudes
are wanted elsewhere -- so a dot product ranks partly by how much text a passage contains.
The three policy documents are roughly eight times the length of a handbook entry, so they
win queries they are only loosely related to.

**The expected fix** restores ``cosine_similarity`` and the import. One line of substance.

**Measured:** 5 tests fail. The named benchmark case is "Who do I tell about a security
incident?", and the symptom in the ticket -- data classification answered from the supplier
policy -- is real and reproducible by hand.

**What separates a strong answer (S1).** The fix is small and findable; the mechanism is
the thing. A candidate who says "it was using a dot product instead of cosine" has found
the line. One who says "these vectors are unnormalised, so their magnitude grows with the
amount of text, and dot-product ranking therefore ranks partly by length" has understood
why it broke, and will recognise the same bug in a system that does not look like this one.

**S2 is the check nobody is asked to do.** Restoring normalisation must not make the long
policy pages unfindable -- "How often are critical suppliers reviewed?" is in the benchmark
precisely so that over-correcting is visible. A candidate who verifies both directions
rather than only the reported regression is doing the job properly.

**Watch for:**

- **Normalising at index time instead.** Pre-normalising the stored vectors also fixes the
  ranking and is a reasonable design -- but the module docstring explains that magnitudes
  are wanted unnormalised, so this trades one documented decision for another without
  saying so. Accept it if they explain the trade; mark engineering quality down if they
  did not notice there was one.
- **Dividing by passage length** as a correction factor. Works approximately, is not
  cosine, and will drift. If tests pass this way, note that the principled version is one
  function call away.
- **Changing the corpus** so the policy pages are shorter. Protected, and it is fixing the
  data to suit the code.
- **Raising ``top_k``** so the right answer appears somewhere in the list. The top hit is
  still wrong and the citations still point at the wrong document.
""",
}


# ---------------------------------------------------------------------------
# ex-043 -- genAI QA chatbot
# ---------------------------------------------------------------------------

EX043 = {
    "slug": "ex-043-an-answer-fell-between-two-chunks",
    "exercise_number": 43,
    "title": "One question became unanswerable and the document still says the answer",
    "exercise_type": ExerciseType.GENAI_CHATBOT,
    "base_app": BaseApp.RAGQA,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "chunk_overlap_removed_splits_facts",
    "time_limit_minutes": 40,
    "expected_time_minutes": 24,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["rag", "chunking", "retrieval", "python"],
    "brief_md": """\
## SUP-927 — "it says it doesn't know, but it's right there in the handbook"

**Reported by:** an employee, then three more
**Severity:** SEV-3

Asked how far in advance a holiday longer than ten days has to be requested, the
assistant says it has nothing in the knowledge base that answers it.

The annual leave page answers it. Two sentences, one after the other: requests go in two
weeks ahead, and ones covering more than ten consecutive days also need director approval.

Asking about either half separately works. Asking the question somebody would actually
ask does not.

### What we know

- Nothing errors. The assistant refuses, which is the behaviour it is supposed to have
  when it genuinely cannot answer — so this looks like correct behaviour until you read
  the document.
- `make test` is red, and the chunking tests are among the failures. One of them asserts
  a property over **every** document in the corpus, not just this one.
- A change went in recently to make the index smaller.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
make ask Q="how far in advance must I request a holiday longer than ten days?"
make ask Q="how much notice do I need to book leave?"
```

The second works. The first does not. That difference is the whole exercise.

### What we need

The question answerable again, and a `NOTES.md` that explains what made it unanswerable —
not merely unlikely to rank. Those are different failures and only one of them can be
fixed by retrieving more passages.
""",
    "definition_of_done": [
        "R1: the chunk-boundary property holds for the whole corpus",
        "R2: the boundary question is answered again",
        "R3: the evaluation set scores 1.0 on exact match",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md distinguishes 'ranked poorly' from 'present in no chunk at all'",
    ],
    "focus_paths": ["src/ragqa/rag/chunker.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_chunker.py::test_every_adjacent_sentence_pair_appears_together_somewhere"
            ),
            "weight": 5,
            "required": True,
            "description": (
                "Every pair of neighbouring sentences in every document appears together "
                "in at least one chunk"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_eval.py::test_the_boundary_question_is_answered",
            "weight": 4,
            "required": True,
            "description": "The reported question is answered end to end",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_eval.py::test_exact_match_is_perfect",
            "weight": 2,
            "required": True,
            "description": "The labelled set is answered exactly again",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including the evaluation gate",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, corpus, evaluation set and fixtures are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Drew the distinction that matters: the fact was not ranked poorly, it "
                "was present in no chunk at all -- so no amount of retrieving more "
                "passages could have found it"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Acknowledged the cost the change was chasing -- overlap does duplicate "
                "part of the index -- and said what it buys, rather than reverting without "
                "engaging with why somebody removed it"
            ),
        },
    ],
    "baseline": baseline("ex-043-an-answer-fell-between-two-chunks"),
    "context_excerpts": [
        {
            "path": "src/ragqa/rag/chunker.py",
            "line_range": "1-15",
            "why": (
                "The module docstring, which states the property overlap exists to "
                "guarantee and why it is invisible until it is missing."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "96-107",
            "why": (
                "'Chunking, and the fact that would otherwise be unretrievable'. Names "
                "the specific document written to have this shape."
            ),
        },
    ],
    "hints": [
        "Run `make test` and start with the chunking failures rather than the "
        "end-to-end ones. One of them asserts a property across the whole corpus.",
        "Ask the two halves of the question separately — both work. Then ask what would "
        "have to be true of the index for the combined question to fail when neither "
        "half does.",
        "`chunk_document` slides a window over the sentences of a document. Look at how "
        "far it advances each time, and what that means for a fact stated across the "
        "boundary between two windows.",
    ],
    "grading_notes": """\
**Root cause.** ``OVERLAP_SENTENCES`` was set to 0. With a three-sentence window advancing
three sentences, a fact spanning the boundary between two windows appears in neither: the
first chunk ends with sentence three, the second begins with sentence four, and the rule
stated across those two sentences exists in no chunk.

**The expected fix** restores ``OVERLAP_SENTENCES = 1``. One line.

**Why this is worth forty minutes despite being a one-line fix.** The symptom is a
*refusal*, which is the system behaving correctly in every visible respect. Nothing throws,
nothing is logged as an error, and the refusal message is the one a well-behaved assistant
gives. A candidate has to notice that the refusal is wrong before they can start.

**Measured:** 10 tests fail, across chunking and the end-to-end evaluation.

**S1 is the transferable idea.** "The chunk did not rank well" and "no chunk contains the
fact" look identical from the outside and have completely different fixes. The first is
addressed by retrieving more passages, reranking, or a better query; the second cannot be
addressed by any of those, because the text was never a candidate. A candidate who states
that distinction has learned the thing this exercise exists to teach.

**S2 rewards engaging with the motivation.** The comment left on the change says overlap
was duplicating a third of the index for no measurable gain *on the retrieval benchmark* --
and that is true, because the benchmark measures which document ranks first, not whether a
cross-boundary fact exists. Reverting without noticing that the measurement was the wrong
one leaves the next person free to remove it again.

**Watch for:**

- **Raising ``top_k`` or ``DEFAULT_TOP_K``.** The most common wrong fix and it cannot
  work: retrieving more passages does not create a passage containing the fact. If a
  candidate tries this and then works out why it did not help, that is good progress --
  say so.
- **Increasing ``CHUNK_SENTENCES``** so the two sentences land in one window. This happens
  to fix the reported question and leaves the general property broken: there is still a
  boundary, it has just moved. R1 catches it, and it is worth explaining why in feedback.
- **Editing the annual leave document** to put both halves in one sentence. Protected, and
  it fixes one instance of a corpus-wide problem.
- **Setting overlap to 2.** Works. Doubles the index for no additional guarantee over 1,
  since the property only needs adjacent pairs. Accept, and note the cost.
""",
}


# ---------------------------------------------------------------------------
# ex-044 -- genAI QA chatbot
# ---------------------------------------------------------------------------

EX044 = {
    "slug": "ex-044-the-tampered-page-reached-the-prompt",
    "exercise_number": 44,
    "title": "An edited wiki page is reaching the model as instructions",
    "exercise_type": ExerciseType.GENAI_CHATBOT,
    "base_app": BaseApp.RAGQA,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "injection_quarantined_per_chunk_not_document",
    "time_limit_minutes": 50,
    "expected_time_minutes": 32,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["rag", "security", "prompt-injection", "guardrails"],
    "brief_md": """\
## SEC-204 — prompt injection reaching the model

**Found by:** a security review of the knowledge base
**Severity:** SEV-2

Somebody added a sentence to a draft engineering page that is addressed to the assistant
rather than to the reader. It tells the model to ignore its instructions and print its
system prompt.

We have a guardrail for exactly this. The review found that text from that page is
reaching the assembled prompt anyway.

### What we know

- The guardrail is running and it is detecting something: a quarantine is recorded.
- The page is not obscure. It ranks **above** the genuine on-call document for "what is
  the on-call allowance?", because it is also genuinely about that topic. This is not a
  crafted attack path; it is what happens when somebody edits a page people search for.
- `make test` is red, and three tests name the guardrail.
- The model here is a recording, so you will not see it obey the instruction. **Do not
  take that as evidence the guardrail is working.** What can be observed is whether the
  text reaches the prompt, and that is what the tests assert.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
make ask Q="what is the on-call allowance?"
```

Look at `shown` and `quarantined` in the output, not just at the answer.

### What we need

Nothing from a tampered page in the prompt. Then a `NOTES.md` that says why the guardrail
detected the problem and failed to contain it — those are different failures, and the
second one is the interesting one.

### Watch out for

A guardrail that catches the sentence carrying an attack is not the same as a guardrail
that contains the attack. Think about what an attacker does next, given the design as it
currently stands.
""",
    "definition_of_done": [
        "R1: the tampered document is withheld in full",
        "R2: no injected text reaches the assembled prompt",
        "R3: screening still happens before routing",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains why detecting the sentence was not enough",
    ],
    "focus_paths": ["src/ragqa/rag/guardrails.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_guardrails.py::test_the_tampered_document_is_quarantined",
            "weight": 5,
            "required": True,
            "description": "No passage from the tampered page survives screening",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_guardrails.py::test_the_injection_never_reaches_the_prompt",
            "weight": 5,
            "required": True,
            "description": "The assembled prompt contains none of the injected text",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_pipeline.py::test_screening_happens_before_routing",
            "weight": 2,
            "required": True,
            "description": "The order of operations is preserved",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including the evaluation gate",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, corpus, evaluation set and fixtures are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Named the attack the per-passage design permits: put the instruction in "
                "one chunk and the payload in the next, and the guardrail withholds the "
                "sentence carrying the attack while serving everything it was protecting"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Reasoned about trust rather than text: whoever wrote the injection had "
                "edit access to the whole page, so the rest of it is not trustworthy "
                "either -- which is why the unit of quarantine is the document"
            ),
        },
        {
            "id": "S3",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Was honest about the limits of pattern matching, and identified the "
                "second layer that still applies when it is evaded"
            ),
        },
    ],
    "baseline": baseline("ex-044-the-tampered-page-reached-the-prompt"),
    "context_excerpts": [
        {
            "path": "src/ragqa/rag/guardrails.py",
            "line_range": "1-25",
            "why": (
                "The module docstring, which argues why retrieved text is untrusted input "
                "and why withholding beats stripping or escaping."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "118-134",
            "why": (
                "'The corpus is not trusted input'. States the unit of quarantine and the "
                "attack that motivates it, and is honest about what pattern matching "
                "cannot do."
            ),
        },
    ],
    "hints": [
        'Run `make ask Q="what is the on-call allowance?"` and read `quarantined` and '
        "`shown` together. Something was withheld. Something else from the same page "
        "was not.",
        "The tampered page is four sentences long and the chunker splits it. Which "
        "chunk carries the injected sentence, and which chunk does not?",
        "`screen` decides what to withhold. Look at what it is deciding *about* — a "
        "passage, or the thing the passage came from — and ask which of those an "
        "attacker controls.",
    ],
    "grading_notes": """\
**Root cause.** ``screen`` quarantines a passage when that passage's own text matches an
injection pattern, ignoring the ``tainted_documents`` set it is given. The tampered page is
four sentences and chunks into two passages; the injection is in the first, so the second
passes screening and reaches the prompt.

**The expected fix** restores the document-level check: a hit is withheld if its own text
matches **or** its document is in ``tainted_documents``.

**Why this is advanced.** The guardrail is visibly working. It detects the injection, logs
a quarantine, and withholds a passage -- so every surface signal says the control is doing
its job. The failure is in the *unit* it operates on, which is only visible if you ask what
an attacker does given the design.

**S1 is the finding.** Chunking splits a page, so an attacker puts the instruction in one
chunk and the content it is meant to influence in the next. A per-passage guardrail then
withholds exactly the sentence carrying the attack and serves everything it was supposed to
protect -- strictly worse than useless, because the quarantine log makes it look handled.

**S2 is the reasoning behind the fix.** The right unit is the document because trust is a
property of who could edit it, not of which sentence happens to match a regex. Whoever
wrote the injection had write access to the whole page. A candidate who gets there has
understood why the fix is not "add more patterns".

**S3 rewards honesty.** Pattern matching will not stop a determined attacker and the module
docstring says so. The prompt's reference section, which marks retrieved text as data, is
the shallower second layer that still applies. A candidate who says the control is partial
and names what backs it up is describing the system accurately.

**Watch for:**

- **Adding more patterns.** Catches this injection and not the next one. It also does not
  fix the split-payload attack at all, since the payload chunk matches nothing. If tests
  pass this way they have not -- R1 asserts the whole document is withheld.
- **Stripping the offending sentence** and serving the rest of the passage. Explicitly
  rejected in the module docstring: the rest of a page somebody has tampered with is not
  trustworthy.
- **Dropping the whole retrieval result** when anything is flagged. Over-correction that
  turns one bad page into a denial of service for every question that happens to rank near
  it. The evaluation set catches it.
- **Filtering at index time only**, so tampered documents never enter the index. A
  defensible design and arguably stronger -- but it must still pass R3, and a candidate
  choosing it should say what happens to a page tampered with *after* indexing.
""",
}


# ---------------------------------------------------------------------------
# ex-045 -- genAI QA chatbot
# ---------------------------------------------------------------------------

EX045 = {
    "slug": "ex-045-citations-point-at-text-the-model-never-saw",
    "exercise_number": 45,
    "title": "A cited passage was only half in the prompt",
    "exercise_type": ExerciseType.GENAI_CHATBOT,
    "base_app": BaseApp.RAGQA,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "context_truncated_mid_passage",
    "time_limit_minutes": 25,
    "expected_time_minutes": 15,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["rag", "prompt-assembly", "citations", "python"],
    "brief_md": """\
## SUP-941 — the context budget is cutting passages in half

**Reported by:** an engineer reading the prompt logs
**Severity:** SEV-3

Somebody was looking at an assembled prompt and noticed a reference passage that stops
mid-sentence. The passage is still labelled with its id, so the model can cite it — and a
citation to a passage the model only partly read is not a citation at all.

Two tests in `tests/test_prompt_builder.py` are failing and they name the behaviour.

### What we know

- A change went in to use the context budget more fully. The reasoning on it is in the
  diff and it is not unreasonable: dropping a whole passage does leave the budget short.
- Nothing errors. The prompts are well-formed and the answers still read correctly.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
```

### What we need

Passages that are either included whole or not included at all, and a `NOTES.md` saying
why half a passage is worse than none of it.
""",
    "definition_of_done": [
        "R1: no passage is truncated to fit the budget",
        "R2: the lowest-ranked passage is dropped when the budget is exceeded",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains why a truncated passage is worse than a dropped one",
    ],
    "focus_paths": ["src/ragqa/rag/prompt_builder.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_prompt_builder.py::test_passages_are_dropped_whole_and_never_truncated"
            ),
            "weight": 5,
            "required": True,
            "description": "Every passage shown appears in the prompt with its text intact",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_prompt_builder.py::test_the_lowest_ranked_passage_is_dropped_first",
            "weight": 3,
            "required": True,
            "description": "Trimming removes whole passages, lowest-ranked first",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R4",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including the evaluation gate",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, corpus, evaluation set and fixtures are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained why this failure leaves no trace: the truncated passage is "
                "still labelled and still citable, so the citation validates, the logs "
                "look clean, and only the answer is quietly wrong"
            ),
        },
    ],
    "baseline": baseline("ex-045-citations-point-at-text-the-model-never-saw"),
    "context_excerpts": [
        {
            "path": "src/ragqa/rag/prompt_builder.py",
            "line_range": "1-21",
            "why": (
                "The module docstring, which states the trimming rule and names the "
                "failure the alternative produces."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "108-117",
            "why": "'Trimming drops whole passages, never halves of them'.",
        },
    ],
    "hints": [
        "Run `make test`. Both failures are in `tests/test_prompt_builder.py` and their "
        "docstrings describe the rule being broken.",
        "`fit_to_budget` decides what goes in the prompt. Compare what it does now when "
        "a passage does not fit against what its own docstring says it should do.",
        "The fix is to drop the passage rather than shorten it. The interesting part is "
        "the writeup: what goes wrong downstream when a passage is half-present?",
    ],
    "grading_notes": """\
**Root cause.** ``fit_to_budget`` truncates a passage to the remaining budget instead of
dropping it. The truncated passage keeps its id, is listed in ``shown``, and is therefore
available to cite.

**The expected fix** restores the drop-whole behaviour. A few lines.

**This is the beginner exercise on this base app** and the time box is short. Two tests
fail, both named for the rule, and the fix is in the function they name.

**The marks are in S1, not in the fix.** The failure mode is worth articulating: a
truncated passage validates as a citation, appears in the audit trail like any other, and
produces an answer grounded in text the model only partly saw. Nothing downstream can
detect it -- citation precision passes, because the id really was shown. A candidate who
explains that has understood why the rule exists rather than merely restoring it.

**Watch for:**

- **Raising ``CONTEXT_BUDGET_CHARS``.** Makes the failing tests pass for the budget they
  use and leaves the behaviour intact for any budget. R1 passes a budget explicitly, so it
  still fails -- but check, because a candidate who tries this has misread the problem as
  being about size rather than about the rule.
- **Truncating at a sentence boundary instead.** Better, still wrong: the passage is still
  partial and still fully citable. If they do this, they have improved the symptom and kept
  the defect.
- **Keeping the truncated passage but removing it from ``shown``.** Now the model sees text
  it cannot cite, which trades one grounding problem for another.
""",
}


# ---------------------------------------------------------------------------
# ex-046 -- genAI QA chatbot
# ---------------------------------------------------------------------------

EX046 = {
    "slug": "ex-046-the-assistant-stopped-answering-what-it-knows",
    "exercise_number": 46,
    "title": "After a tuning change it says it doesn't know far too often",
    "exercise_type": ExerciseType.GENAI_CHATBOT,
    "base_app": BaseApp.RAGQA,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "refusal_threshold_raised_past_real_questions",
    "time_limit_minutes": 40,
    "expected_time_minutes": 24,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["rag", "routing", "thresholds", "evaluation"],
    "brief_md": """\
## SUP-953 — the assistant has become useless

**Reported by:** most of the company
**Severity:** SEV-2

Since a change last week the assistant refuses a large share of perfectly ordinary
questions. Annual leave, passwords, on-call shifts — things plainly in the handbook.

The change was made for a good reason: we had a run of answers that turned out to rest on
a passage only loosely related to the question, and the threshold was raised so the
assistant would only answer when it was confident.

### What we know

- It still refuses everything it *should* refuse. The problem is entirely on the other
  side.
- `make eval` is the fastest way to see the scale of it. `make evald` lists every question
  so you can see which ones went.
- A healthy build scores 1.0 on all four metrics.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make eval
make evald
```

### What we need

Both sides working: nothing refused that the handbook answers, and nothing answered that
it does not. **Simply reverting the number is not the answer we are looking for** — the
concern that prompted the change was real, and `NOTES.md` should say how the system
addresses it, or what you would do if it does not.

### Watch out for

There are two thresholds here and they are not interchangeable. Read what each is for
before moving either.
""",
    "definition_of_done": [
        "R1: no answerable question is refused",
        "R2: refusal behaviour scores 1.0 on balanced accuracy",
        "R3: the evaluation set scores 1.0 on exact match",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md addresses the concern that motivated the change",
    ],
    "focus_paths": ["src/ragqa/rag/router.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_eval.py::test_no_answerable_question_was_refused",
            "weight": 5,
            "required": True,
            "description": "Every question the corpus answers is answered",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_eval.py::test_refusal_behaviour_is_perfect",
            "weight": 4,
            "required": True,
            "description": "Both classes correct, each weighted equally",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_eval.py::test_exact_match_is_perfect",
            "weight": 2,
            "required": True,
            "description": "The labelled set is answered exactly again",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including the evaluation gate",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, corpus, evaluation set and fixtures are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Engaged with the motivating concern rather than reverting silently: "
                "explained which of the two signals actually guards against a loosely-"
                "related passage, and why raising the other one was the wrong lever"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Used the evaluation set as the instrument it is -- both classes, not just "
                "the one in the ticket -- and noted that tuning against refusals alone "
                "converges on refusing everything"
            ),
        },
    ],
    "baseline": baseline("ex-046-the-assistant-stopped-answering-what-it-knows"),
    "context_excerpts": [
        TWO_SIGNALS_EXCERPT,
        {
            "path": "src/ragqa/rag/router.py",
            "line_range": "1-28",
            "why": (
                "The module docstring, which gives the measured distributions for both "
                "signals and states what each is for -- including that similarity is "
                "deliberately the permissive one."
            ),
        },
    ],
    "hints": [
        "`make evald` lists every question with its scores. Look at which ones are now "
        "refused and what they have in common.",
        "`make ask` prints the routing decision, including both numbers and the reason. "
        "Run it on a question that is now refused and read which threshold rejected it.",
        "There are two thresholds in `router.py` and the module docstring explains which "
        "one is the decisive signal and which is the permissive backstop. One of them has "
        "been moved into a role it was never meant for.",
    ],
    "grading_notes": """\
**Root cause.** ``MIN_SCORE`` was raised from 0.12 to 0.30. That is the *similarity*
threshold, which the module docstring describes as deliberately permissive -- it exists to
catch "nothing ranked at all", not to be the decision. The decisive signal is
``MIN_COVERAGE``, which is collision-free and already doing the job the change was aiming
at.

**The expected fix** restores ``MIN_SCORE = 0.12``.

**Measured:** 8 tests fail, concentrated in the end-to-end evaluation. No cassette misses
and no errors, because a refusal never reaches the model -- the system fails quietly and
politely, which is what makes it a support problem rather than an alerting one.

**S1 is the exercise.** Reverting the constant passes every check. What distinguishes a
good answer is addressing the concern that prompted the change: answers resting on a
loosely-related passage. The relevant control is coverage -- the fraction of the question's
own terms that appear verbatim in the passage -- and it was already set correctly. Raising
similarity instead traded a real problem for a bigger one, and a candidate who explains
which lever does what has understood a system with two interacting thresholds.

**S2** rewards treating the evaluation set as an instrument. Both classes are in it
precisely because tuning against one converges on a degenerate system: raise the thresholds
until nothing is answered, and refusal recall is perfect.

**Watch for:**

- **Lowering ``MIN_COVERAGE`` to compensate** while leaving ``MIN_SCORE`` high. Can be made
  to pass the answerable side and weakens the signal that actually prevents nonsense. If
  both R1 and R2 pass this way, check which constants moved -- it is a symptom patch.
- **Removing a threshold entirely.** Passes the answerable side, fails the refusal side as
  soon as a hash collision ranks an unanswerable question.
- **Reverting with no comment on the motivation.** Correct, and earns no stretch. Worth
  saying in feedback that the next person will raise it again.
- **Editing the evaluation set** so the refused questions are marked unanswerable.
  Protected. It is also the purest possible example of fixing the measurement.
""",
}


# ---------------------------------------------------------------------------
# ex-047 -- genAI eval framework
# ---------------------------------------------------------------------------

EX047 = {
    "slug": "ex-047-the-score-rose-while-the-answers-got-worse",
    "exercise_number": 47,
    "title": "Our answer-quality score went up after answers got longer",
    "exercise_type": ExerciseType.EVAL_FRAMEWORK,
    "base_app": BaseApp.RAGQA,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "f1_reports_recall_and_rewards_padding",
    "time_limit_minutes": 35,
    "expected_time_minutes": 21,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["evaluation", "metrics", "f1", "python"],
    "brief_md": """\
## EVAL-61 — the quality metric is rewarding verbosity

**Reported by:** whoever has to present these numbers
**Severity:** SEV-3

We changed the prompt to make answers more complete, and the answer-quality score went up.
Then somebody read the answers. They are padded — the right sentence buried in four
others, with the extra material lifted from whichever passages happened to be retrieved.

A metric that improves when that happens is not measuring answer quality.

### What we know

- `make test` is red and the failures are in `tests/test_metrics.py`. Their docstrings
  work the arithmetic out by hand.
- **`make eval` reports 1.0 on everything.** That is not a contradiction and it is worth
  understanding before you start: the system is currently answering correctly, so a
  metric that is too generous has nothing to be generous about. This is exactly why a
  broken metric can sit in a repository for a year.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
```

### What we need

A metric that scores a padded answer below a tight one, and a `NOTES.md` that says what
the metric was actually computing.
""",
    "definition_of_done": [
        "R1: the padding test passes with its hand-computed value",
        "R2: a tight answer scores above a padded one",
        "R3: token overlap is counted as a multiset",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md names what the metric was computing instead of F1",
    ],
    "focus_paths": ["src/ragqa/eval/metrics.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_metrics.py::test_f1_refuses_to_reward_padding",
            "weight": 5,
            "required": True,
            "description": "A padded answer scores 0.435, not 1.0",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_metrics.py::test_f1_rewards_a_tight_answer_over_a_padded_one",
            "weight": 3,
            "required": True,
            "description": "Conciseness is scored above verbosity",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_metrics.py::test_f1_counts_tokens_as_a_multiset",
            "weight": 2,
            "required": True,
            "description": "Repeating a token does not match it more times than it occurs",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including the evaluation gate",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, corpus, evaluation set and fixtures are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Named the quantity precisely -- it was returning recall -- and explained "
                "why recall alone rewards padding while precision alone rewards terseness, "
                "so only the pair resists both"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Understood why the end-to-end report stayed at 1.0: a too-generous metric "
                "has nothing to be generous about while the system is answering correctly, "
                "which is how metric bugs survive"
            ),
        },
    ],
    "baseline": baseline("ex-047-the-score-rose-while-the-answers-got-worse"),
    "context_excerpts": [
        METRICS_EXCERPT,
        {
            "path": "src/ragqa/eval/metrics.py",
            "line_range": "1-31",
            "why": (
                "The module docstring, which pairs each metric with the specific way of "
                "being fooled it was chosen against."
            ),
        },
    ],
    "hints": [
        "Run `make test`. The failures are in `tests/test_metrics.py` and the first one "
        "derives the expected value token by token in its docstring.",
        "Work out by hand what the current implementation returns for that test's input, "
        "then ask which standard quantity that is.",
        "`token_f1` computes an overlap and then returns something derived from it. "
        "Compare what it divides by against what an F1 score is defined to be.",
    ],
    "grading_notes": """\
**Root cause.** ``token_f1`` returns ``overlap / len(gold_tokens)`` -- recall -- rather than
the harmonic mean of precision and recall. An answer containing every gold token scores
1.0 no matter how much else it contains, so padding is free and verbosity is rewarded.

**The expected fix** restores precision, recall and their harmonic mean.

**Measured:** 3 tests fail, all in ``tests/test_metrics.py``. The end-to-end evaluation
stays at 1.0 throughout.

**That last point is the most important thing in this exercise and S2 is for it.** A
loosened metric cannot show on a system that is already answering correctly: at baseline
the prediction equals the reference, so precision, recall and F1 are all 1.0 and the defect
is invisible in every aggregate number. It becomes visible only against an input
constructed to expose it, which is what the unit tests are. A candidate who notices that
``make eval`` is clean and works out *why* that is consistent with a real bug has
understood how metric defects survive -- they are dormant until the system degrades, and
then they hide the degradation.

**S1 wants the quantity named.** "It was returning recall" is the answer. The follow-on --
recall alone rewards padding, precision alone rewards terseness, and only the pair resists
both -- is what shows they understand why F1 is the shape it is rather than having
pattern-matched a formula.

**Watch for:**

- **Returning precision instead.** Symmetrically wrong, and it will pass the padding test
  while failing in the opposite direction. R2 and R3 catch it.
- **Hardcoding 0.435** or special-casing the test's input. If any survives, that is a
  symptom patch -- set the flag.
- **Using sets rather than ``Counter``.** Fixes the padding case and breaks the multiset
  property, which R3 exists for.
- **Changing the test's expected value.** Protected. Hard F.
""",
}


# ---------------------------------------------------------------------------
# ex-048 -- genAI eval framework
# ---------------------------------------------------------------------------

EX048 = {
    "slug": "ex-048-citation-precision-counts-sources-nobody-read",
    "exercise_number": 48,
    "title": "Citation precision stopped falling when citations got worse",
    "exercise_type": ExerciseType.EVAL_FRAMEWORK,
    "base_app": BaseApp.RAGQA,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "citation_precision_measured_against_corpus",
    "time_limit_minutes": 45,
    "expected_time_minutes": 27,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["evaluation", "metrics", "citations", "grounding"],
    "brief_md": """\
## EVAL-68 — citation precision is not measuring grounding

**Reported by:** the review of last quarter's quality report
**Severity:** SEV-2

Citation precision is the number we use to claim answers are grounded. The reviewer asked
what exactly it verifies about a citation, and the answer turned out to be: that it looks
like a citation.

A change went in to stop "marking good answers down whenever ranking shifted". Since then
a citation counts as supported if its id is well-formed.

### What we know

- One test is failing. Its docstring explains what a citation is supposed to mean.
- **`make eval` reports 1.0 on everything**, both before and after the change. That is
  consistent with the bug rather than evidence against it, and understanding why is most
  of this exercise.
- The distinction the metric is supposed to draw is subtle and worth getting precisely
  right before you change anything. `ARCHITECTURE.md` states it.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
```

### What we need

A citation metric that measures grounding, and a `NOTES.md` that says what claim the
number supports — specifically, what it does and does not let us tell a customer.

### Watch out for

There are three sets in play: what the answer cited, what the reference says should have
been cited, and what was actually put in front of the model. Precision and recall are
measured against different ones, and swapping them produces a plausible number that means
something else.
""",
    "definition_of_done": [
        "R1: a citation to a passage that was never shown is not counted as supported",
        "R2: the whole suite is green, with no test skipped, deleted or weakened",
        "R3: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md states what claim citation precision supports",
    ],
    "focus_paths": ["src/ragqa/eval/metrics.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_metrics.py::test_a_citation_to_an_unretrieved_passage_is_not_supported"
            ),
            "weight": 6,
            "required": True,
            "description": "Precision is 0.5 when one of two citations was never retrieved",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 4,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R3",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including the evaluation gate",
        },
        {
            "id": "R4",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, corpus, evaluation set and fixtures are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Articulated the distinction precisely: a citation naming a real document "
                "the model never saw is fabricated, because nothing it said about that "
                "document came from reading it -- existence is not grounding"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained why the headline numbers never moved, and why that makes this "
                "class of bug durable: the metric only matters once the system starts "
                "citing things it should not, which is when it stops working"
            ),
        },
        {
            "id": "S3",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Kept precision and recall measured against the right sets -- shown for "
                "precision, gold for recall -- rather than fixing one by breaking the other"
            ),
        },
    ],
    "baseline": baseline("ex-048-citation-precision-counts-sources-nobody-read"),
    "context_excerpts": [
        METRICS_EXCERPT,
        {
            "path": "src/ragqa/eval/metrics.py",
            "line_range": "138-180",
            "why": (
                "``citation_metrics`` and its note, which states that precision is measured "
                "against what was retrieved and not against the corpus, and why checking "
                "the corpus passes exactly the case worth catching."
            ),
        },
        {
            "path": "src/ragqa/rag/guardrails.py",
            "line_range": "1-25",
            "why": (
                "The same distinction enforced at runtime by ``validate_citations``. The "
                "metric and the guardrail are supposed to agree about what a citation "
                "means; one of them has stopped."
            ),
        },
    ],
    "hints": [
        "Run `make test`. One test fails, and its docstring names the exact case: a real "
        "document that was never retrieved for this question.",
        "`citation_metrics` takes three collections. Work out which one precision should "
        "be measured against, and what the current implementation checks instead.",
        "Compare the metric against `guardrails.validate_citations`, which enforces the "
        "same idea at runtime. They disagree, and the runtime one is right.",
    ],
    "grading_notes": """\
**Root cause.** ``citation_metrics`` counts a citation as supported when its id matches the
chunk-id *pattern*, rather than when it appears in the set of passages actually shown to the
model. A membership check was replaced by a format check.

**The expected fix** restores ``supported = len(cited_set & retrieved_set)``.

**Why this is advanced despite a one-line fix.** Nothing in any aggregate moves. The
end-to-end report is 1.0 before and after, because the system currently cites only passages
it was shown -- so a metric that would also accept other citations never gets the chance.
The defect is dormant, and it becomes load-bearing precisely when the system starts
fabricating citations, which is the moment the number is supposed to catch it.

**S1 wants the distinction stated.** A citation naming a real document the model never saw
is fabricated. The document existing is irrelevant: nothing the answer said about it came
from reading it, because it was never read. "Exists in the corpus" and "was the basis for
this answer" are different claims, and only the second is grounding.

**S2 is the durability point.** This is the second metric defect in this repository with
the same signature -- invisible while things work -- and a candidate who generalises from
it has learned something about evaluation code in general: it is the one part of a system
that is never exercised by the system working correctly, so it needs tests built from
constructed failures rather than from real runs.

**S3 is a trap worth watching.** The function measures precision against ``retrieved`` and
recall against ``gold``, which is correct and easy to "tidy up" into using one set for both.
Doing so makes the failing test pass and silently redefines recall.

**Watch for:**

- **Measuring precision against ``gold``.** Passes R1 and turns precision into a second
  recall. The suite may not catch it; read the diff.
- **Making ``validate_citations`` looser** to match the metric. Exactly backwards -- the
  runtime check is the correct one, and loosening it would let fabricated citations reach
  users.
- **Adding a corpus parameter** so existence can be checked properly. Doubles down on the
  wrong idea with more machinery.
- **Editing the test.** Protected. Hard F.
""",
}


# ---------------------------------------------------------------------------
# ex-049 -- genAI eval framework
# ---------------------------------------------------------------------------

EX049 = {
    "slug": "ex-049-the-refusal-metric-rewards-answering-everything",
    "exercise_number": 49,
    "title": "A bot that answers everything scores 79% on knowing when to stop",
    "exercise_type": ExerciseType.EVAL_FRAMEWORK,
    "base_app": BaseApp.RAGQA,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "refusal_scored_as_plain_accuracy",
    "time_limit_minutes": 45,
    "expected_time_minutes": 27,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["evaluation", "metrics", "class-imbalance", "statistics"],
    "brief_md": """\
## EVAL-72 — the refusal metric cannot see the thing it measures

**Reported by:** a reviewer preparing the board update
**Severity:** SEV-2

Refusal correctness is the number we use to claim the assistant knows when to stop. The
reviewer asked what a system that never refused anything would score on it.

Nobody knew. The answer is about 79%.

### What we know

- Three tests are failing, all in `tests/test_metrics.py`. Two of them construct exactly
  the degenerate systems a metric like this has to be able to see.
- The change that caused it has a rationale attached, and the rationale is not silly:
  the evaluation set has far more answerable questions than unanswerable ones, and the
  previous number did swing on a small number of cases.
- **`make eval` reports 1.0.** The current system refuses correctly, so a metric that
  cannot detect bad refusal behaviour has no bad behaviour to miss.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
```

### What we need

A number that a system answering everything cannot score well on, and a `NOTES.md` that
explains what the previous rationale got right and what it got wrong — because it was half
right, and the half it got right will come back.
""",
    "definition_of_done": [
        "R1: a system that answers everything scores 0.5",
        "R2: a system that refuses everything also scores 0.5",
        "R3: each class is weighted equally regardless of its size",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md engages with the imbalance argument rather than dismissing it",
    ],
    "focus_paths": ["src/ragqa/eval/metrics.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_metrics.py::test_balanced_accuracy_exposes_a_system_that_never_refuses"
            ),
            "weight": 5,
            "required": True,
            "description": "Plain accuracy 0.794, balanced accuracy 0.5",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_metrics.py::"
                "test_balanced_accuracy_also_exposes_a_system_that_always_refuses"
            ),
            "weight": 3,
            "required": True,
            "description": "The mirror-image degenerate system also scores 0.5",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_metrics.py::test_each_class_is_weighted_equally_regardless_of_size"
            ),
            "weight": 3,
            "required": True,
            "description": "One unanswerable question weighs as much as twenty-seven others",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including the evaluation gate",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, corpus, evaluation set and fixtures are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Explained the mechanism: on an imbalanced set plain accuracy is mostly a "
                "measure of how often the system answers, so the one behaviour being "
                "measured contributes almost nothing to it"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Took the original rationale seriously -- a small unanswerable set does "
                "make the number noisier -- and separated the real problem (variance from "
                "few samples) from the wrong fix (weighting by frequency)"
            ),
        },
    ],
    "baseline": baseline("ex-049-the-refusal-metric-rewards-answering-everything"),
    "context_excerpts": [
        METRICS_EXCERPT,
        {
            "path": "src/ragqa/eval/metrics.py",
            "line_range": "199-240",
            "why": (
                "``refusal_metrics`` and its note, which states why the headline is "
                "balanced accuracy and keeps plain accuracy visible alongside it so the "
                "gap between the two can be seen."
            ),
        },
    ],
    "hints": [
        "Run `make test`. Two of the failures construct a system that answers everything "
        "and one that refuses everything, and assert what each should score.",
        "Work out by hand what the current implementation gives for a system that answers "
        "all 34 questions, 27 of which are answerable.",
        "`refusal_metrics` already computes the two per-class recalls correctly. Look at "
        "what the headline field is being assigned from, and what it was before.",
    ],
    "grading_notes": """\
**Root cause.** ``balanced_accuracy`` is assigned plain accuracy -- correct decisions over
all decisions -- instead of the mean of the two per-class recalls. Both recalls are still
computed correctly and reported; only the headline is wrong.

**The expected fix** restores ``(answer_recall + refusal_recall) / 2``.

**The arithmetic a candidate should reproduce.** The set is 27 answerable and 7
unanswerable. A system that answers everything gets 27 right and 7 wrong: plain accuracy
27/34 = **0.794**, balanced accuracy (1.0 + 0.0)/2 = **0.5**. The first reads like a decent
system; the second is the truth.

**S1 is the mechanism.** On an imbalanced set, plain accuracy is dominated by the majority
class -- so it is mostly a measure of how often the system answers, and the behaviour the
metric exists to measure contributes almost nothing. Balanced accuracy gives each class
equal weight regardless of how many of each the set happens to contain.

**S2 is the harder half and the reason this is advanced.** The rationale on the change is
*partly correct*: with only 7 unanswerable questions, each one is worth 1/14 of the headline
number, so a single case flipping moves it by 7 points. That is real and it will come back
the next time somebody finds the number noisy. The right response is more unanswerable
questions in the set, or a reported confidence interval -- not weighting the class down to
the point where it stops mattering. A candidate who separates "this estimate has high
variance" from "this estimate is measuring the wrong thing" is doing the thing the exercise
is for.

**Watch for:**

- **Weighting by something other than 1/2.** Any weighting derived from class frequency
  reintroduces the bug in softer form. R3 is there for this.
- **Reporting only balanced accuracy** and dropping plain accuracy. The two are kept side
  by side deliberately, because the gap between them is itself informative.
- **Computing an F1 of the two recalls** instead of their mean. Defensible and different;
  it penalises the degenerate cases harder. R1 asserts 0.5 exactly, so it fails -- if a
  candidate argues for it, the argument is good even though the check is not satisfied.
  Note it as a reasonable disagreement rather than a misunderstanding.
- **Adding unanswerable questions to the evaluation set** to fix the imbalance instead.
  The right instinct, wrong file -- ``eval/**`` is protected, and the metric would still be
  wrong on any future set.
""",
}


# ---------------------------------------------------------------------------
# ex-050 -- fix a critical bug fast
# ---------------------------------------------------------------------------

EX050 = {
    "slug": "ex-050-every-citation-lands-one-passage-too-far",
    "exercise_number": 50,
    "title": "Every source link opens the paragraph after the one quoted",
    "exercise_type": ExerciseType.CRITICAL_BUG,
    "base_app": BaseApp.RAGQA,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "chunk_id_off_by_one_misattributes_citations",
    "time_limit_minutes": 25,
    "expected_time_minutes": 15,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["rag", "citations", "off-by-one", "incident"],
    "brief_md": """\
## INC-3410 — citations point at the wrong passage

**Severity:** SEV-1, ongoing
**Reported by:** an employee who clicked a source link

Somebody followed a citation to check an answer about sick pay and landed on a paragraph
about something else. Checking a few more: every citation is off by one. The answers are
right. The sources under them point one passage further on than the text they came from.

For an assistant whose entire claim is that its answers are grounded, a citation that
points somewhere else is worse than no citation — people check the link, see unrelated
text, and conclude the assistant made the answer up.

### What we know

- `make test` is red and several failures mention chunk ids.
- The answers themselves are unaffected. Retrieval is fine; what is wrong is the label.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
make ask Q="when do I need a fit note?"
```

Compare the `citations` in the output against the passage the answer actually came from.

### What we need

Fix it — this is live and people are losing confidence in the answers. Then `NOTES.md`:
how long this has been true, and whether anything else in the system depends on chunk ids
being what they claim to be.
""",
    "definition_of_done": [
        "R1: a chunk's id matches its position in the document",
        "R2: gold citations in the evaluation set resolve to real chunks",
        "R3: citation precision is perfect again",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says what else depends on chunk ids being correct",
    ],
    "focus_paths": ["src/ragqa/rag/chunker.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_chunker.py::test_chunk_ids_match_their_position",
            "weight": 5,
            "required": True,
            "description": "``<doc_id>#<index>`` with the index counting from zero",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_cassettes.py::test_gold_citations_name_real_chunks",
            "weight": 3,
            "required": True,
            "description": "Every gold citation resolves to a chunk that exists",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_eval.py::test_citation_precision_is_perfect",
            "weight": 3,
            "required": True,
            "description": "Citations are supported by what was shown",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including the evaluation gate",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, corpus, evaluation set and fixtures are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Traced what else depends on chunk ids: the citation validator compares "
                "them against what was shown, the evaluation set's gold citations are "
                "written in terms of them, and both break quietly rather than loudly"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noted that answers were never wrong -- only the attribution -- and why "
                "that is still a serious failure for a system whose claim is grounding"
            ),
        },
    ],
    "baseline": baseline("ex-050-every-citation-lands-one-passage-too-far"),
    "context_excerpts": [
        {
            "path": "src/ragqa/rag/chunker.py",
            "line_range": "28-68",
            "why": (
                "The ``Chunk`` definition, whose docstring says why a stable id matters: "
                "it is what a citation refers to, so it must not move."
            ),
        },
        RECORDED_MODEL_EXCERPT,
    ],
    "hints": [
        "Run `make test`. One failure names chunk ids and their position directly.",
        '`make ask Q="when do I need a fit note?"` prints the citations. Compare them '
        "against where the answer's text actually appears.",
        "`chunk_document` builds each chunk's id as it goes. Look at the expression it "
        "uses for the index, and compare it against the ``index`` field set beside it.",
    ],
    "grading_notes": """\
**Root cause.** ``chunk_document`` builds ``chunk_id`` as ``f"{doc_id}#{len(chunks) + 1}"``
while setting ``index=len(chunks)``. The id and the position disagree by one, so every
citation names the passage after the one it came from. The last chunk of each document
gets an id that resolves to nothing at all.

**The expected fix** removes the ``+ 1``.

**This is the beginner exercise and the time box is short.** The failing test names the
property in its own name, and the fix is one token. What is being tested is whether a
candidate can work quickly and still write up a SEV-1 properly.

**S1 is the part worth marks.** Chunk ids are not cosmetic: ``validate_citations``
compares them against what was shown, the evaluation set's gold citations are written in
terms of them, and the ``Chunk`` docstring says explicitly that a citation refers to one.
All of those break *quietly* -- a citation that resolves to the wrong passage still
validates, because the wrong passage was also shown. A candidate who traces that is doing
blast-radius analysis rather than just the ticket.

**S2** rewards being precise about severity. No answer was ever wrong; only the
attribution was. For most systems that is minor. For one whose entire claim is that its
answers are grounded in a named source, a citation that opens unrelated text is worse than
no citation -- the reader concludes the answer was invented.

**Watch for:**

- **Changing ``index`` to match the id** rather than the other way round. Makes the two
  agree at the wrong value: ids now start at 1, every existing gold citation is off, and R2
  fails. If R1 passes and R2 does not, this is what happened.
- **Adjusting the gold citations** in the evaluation set to match the new ids. Protected,
  and it is correcting the reference to match the bug.
- **Fixing it in ``validate_citations``** by comparing with an offset. Papers over the id
  scheme and leaves every stored citation and every log line wrong.
""",
}


#: Every ragqa exercise, in catalog order.
EXERCISES: list[dict] = [EX042, EX043, EX044, EX045, EX046, EX047, EX048, EX049, EX050]
