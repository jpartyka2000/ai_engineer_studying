# tenantsaas — usage-based billing platform

A multi-tenant B2B SaaS backend. Customers ("tenants") own projects, the metering
pipeline writes billable `LineItem` rows continuously, and at the end of each
billing period those items are swept into an `Invoice`.

## Getting started

Everything runs in Docker; dependencies are already baked into the image, so there
is no `pip install` step.

```bash
docker compose up -d --wait   # or: make up
make migrate
make seed
make test
```

The database is published on the host port in your `.env` (`WS_POSTGRES_PORT`), so
you can point `psql` or a GUI client at it:

```bash
psql "postgresql://postgres:postgres@localhost:$WS_POSTGRES_PORT/tenantsaas"
# or, from inside the container:
make psql
```

## Common tasks

| Command | What it does |
|---|---|
| `make test` | Full suite. **This is exactly what grading runs.** |
| `make test-fast` | Stop at the first failure |
| `make ci` | Run the CI pipeline locally (`ci/run_ci.sh`) |
| `make logs` | Tail the app logs |
| `make shell` | Bash inside the app container |
| `make reset` | Tear down and rebuild from scratch |

## The API

All endpoints except `/healthz` require an `X-Api-Key` header identifying the
tenant. Seeded keys are `key-acme-0001`, `key-globex-0002`, `key-initech-0003`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness. No auth. |
| GET | `/projects` | The caller's projects |
| GET | `/usage?period_start=&period_end=` | Period totals, nothing persisted |
| POST | `/invoices/create` | Build a draft invoice |
| GET | `/invoices` | The caller's invoices |

```bash
curl -s "http://localhost:$WS_APP_PORT/usage?period_start=2026-03-01&period_end=2026-03-31" \
     -H "X-Api-Key: key-acme-0001"
```

## Billing periods are inclusive

A period of `2026-03-01` to `2026-03-31` covers **every** line item created on the
31st, right up to `23:59:59`. This trips people up because `LineItem.created_at` is
a timestamp while the period bounds are dates — compare them directly and the
database coerces the date to midnight, silently dropping the final day.

## CI

`.github/workflows/ci.yml` defines the pipeline. `ci/run_ci.sh` is an executable
mirror of the same steps and is what runs locally and in grading — if you change
one, change both.

## Notes on the deployment

Production runs on Amazon RDS. The RDS instance identifier, parameter group,
IAM-auth setting and read-replica endpoint live in `.env` and are read into
`settings.RDS`. Locally that is a plain Postgres container standing in for RDS, so
anything RDS-specific is configuration only and cannot be exercised here.

See `ARCHITECTURE.md` for how the tenant boundary is enforced.
