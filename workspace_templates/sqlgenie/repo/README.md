# sqlgenie

Ask a question in English, get an answer from **your own data only**.

```
question ──▶ recorded model ──▶ generated SQL ──▶ tenant rewrite ──▶ Postgres (RLS)
                                                        ▲                  ▲
                                                 security boundary    second layer
```

## Getting started

```bash
cp .env.example .env     # only needed if you are not using the exercise harness
make up                  # build the image, start Postgres and the API
make migrate             # apply the SQL migrations
make seed                # load two tenants' worth of development data
make test                # run the suite
```

`make help` lists every target.

Ask something:

```bash
make ask Q="Who are our top 10 customers by total order value?"
```

Or over HTTP, on the port in your `.env`:

```bash
curl -s -H "X-Api-Key: acme-dev-key" -H "Content-Type: application/json" \
     -d '{"question":"How many orders are in each status?"}' \
     localhost:$WS_APP_PORT/v1/ask | jq
```

Two development tenants are seeded, `acme` and `borg`, with keys `acme-dev-key` and
`borg-dev-key`. **Their data is identical except for `tenant_id`** — see `ARCHITECTURE.md`
for why that is deliberate.

## Layout

| Path | What lives there |
|---|---|
| `src/sqlgenie/nl2sql/policy/` | **The security boundary.** Rewrites generated SQL to constrain every read to one tenant. |
| `src/sqlgenie/nl2sql/catalog.py` | What the generator may query, and which tables carry a tenant. |
| `src/sqlgenie/nl2sql/prompt.py` | Prompt assembly. Every byte is part of a cassette key. |
| `src/sqlgenie/nl2sql/pipeline.py` | generate → scope → execute, audited on every exit. |
| `src/sqlgenie/llm/` | The recorded model. No network calls anywhere in this service. |
| `src/sqlgenie/tenancy/` | API key → tenant, and the request-scoped tenant context. |
| `db/migrations/` | Schema, the restricted application role, and row-level security. |
| `fixtures/recordings.jsonl` | The authored recording transcript. Readable; diffable. |
| `fixtures/llm_cassettes/` | The same responses, keyed by hash. What the service looks up. |
| `attack/prompts.jsonl` | 18 adversarial cases with their expected outcomes. |

## Running the tests

```bash
make test        # everything, inside the container
make test-unit   # only the tests that need no database
make security    # only the cross-tenant suite
make replay      # run the adversarial corpus through the policy
```

Tests that need Postgres are marked `db`; the cross-tenant suite is also marked
`security`. A missing database makes them **fail rather than skip** — a skipped security
test is a green security test.

The policy and cassette tests need no database and no network, and CI asserts that by
running them with both pointed at dead ports.

## The adversarial corpus

`attack/prompts.jsonl` holds 18 cases, each naming what it probes and why. Seventeen
expect the query to be constrained or refused; **one expects it to be allowed** — a
legitimate cross-tenant question about shared reference data. That case is the control.
Without it, "refuse everything" would pass the whole file.

```bash
make replay      # => {"cases": 18, "mismatches": [], "ok": true}
```

## Editing the prompt or the schema

Both feed the cassette key, so changing either invalidates every recorded response:

```bash
make cassettes   # re-derive cassettes from fixtures/recordings.jsonl
```

`tests/test_cassettes.py` fails loudly if you forget, and names this command.

## CI

`ci/run_ci.sh` is the executable mirror of `.github/workflows/ci.yml`. There is no GitHub
runner here, so the workflow is the artifact you read and the script is what actually
runs — by `make ci` and by the grading harness. Change one and you must change the other.
