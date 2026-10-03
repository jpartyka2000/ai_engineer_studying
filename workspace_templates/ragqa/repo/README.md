# ragqa

Answers questions about company policy from the internal knowledge base — or says it
cannot, which is most of the point.

```
question ─▶ retrieve ─▶ screen ─▶ route ─▶ assemble ─▶ generate ─▶ validate citations
                                    │
                                    └─▶ refuse, without calling the model
```

## Getting started

```bash
cp .env.example .env     # only needed if you are not using the exercise harness
make up                  # build the image, start Postgres and the API
make migrate             # create the conversation tables
make test                # run the suite
make eval                # score the system against the labelled set
```

`make help` lists every target.

Ask something:

```bash
make ask Q="how long is probation?"
make ask Q="how do I cook a risotto?"     # watch it refuse, and say why
```

Or over HTTP, on the port in your `.env`:

```bash
curl -s -H "Content-Type: application/json" \
     -d '{"question":"When are deployments frozen?"}' \
     localhost:$WS_APP_PORT/v1/ask | jq
```

## Layout

| Path | What lives there |
|---|---|
| `src/ragqa/rag/retriever.py` | The index. Two scores per hit: similarity and lexical coverage. |
| `src/ragqa/rag/router.py` | **Whether to answer at all.** Both signals must agree. |
| `src/ragqa/rag/guardrails.py` | Withholds tampered documents; validates citations. |
| `src/ragqa/rag/chunker.py` | Overlapping passages, so no fact falls between two chunks. |
| `src/ragqa/rag/prompt_builder.py` | Assembly, and trimming by whole passages. |
| `src/ragqa/eval/metrics.py` | The four numbers, as pure functions. |
| `corpus/documents.jsonl` | The knowledge base. Authored, readable, editable. |
| `fixtures/recordings.jsonl` | What the model said. Readable and diffable. |
| `fixtures/llm_cassettes/` | The same, keyed by hash. What the service looks up. |
| `eval/questions.jsonl` | The labelled set: 27 answerable, 7 that must be refused. |

## The evaluation set

```bash
make eval      # the five headline numbers
make evald     # with every question listed
```

A healthy build scores **1.0 on all four metrics**, and CI fails if any drops. That is
deliberate: there is nothing to argue about. Anything below 1.0 means something that
worked has stopped working, and `make evald` says which question.

The set is imbalanced on purpose — far more answerable questions than unanswerable ones,
because that is the ratio people ask in. It is also why refusal is reported as *balanced*
accuracy: a system that answers everything scores 0.794 on plain accuracy and 0.500 on
balanced.

## Running the tests

```bash
make test        # everything, inside the container
make test-unit   # only the tests that need no database
```

Retrieval, generation and scoring need neither a database nor a network, and CI asserts
that by running them with both pointed at dead ports. Tests needing Postgres are marked
`db` and **fail rather than skip** when it is missing — a skipped test is green.

## Editing things

**The corpus** can be edited freely. Chunking, the index and the vectoriser are all
rebuilt at start-up, and no cassette is invalidated — keys depend on the question, not on
what was retrieved.

**The system prompt** is part of the cassette key. Change it and every recorded answer
stops resolving:

```bash
make cassettes   # re-derive cassettes from fixtures/recordings.jsonl
```

`tests/test_cassettes.py` fails loudly if you forget, and names this command.

## CI

`ci/run_ci.sh` is the executable mirror of `.github/workflows/ci.yml`. There is no GitHub
runner here, so the workflow is the artifact you read and the script is what actually
runs — by `make ci` and by the grading harness. Change one and you must change the other.
