# Architecture

## Layers

```
HTTP request
  │
  ├─ tenants/middleware.py     resolve X-Api-Key → Tenant, set the context var
  │
  ├─ api/views.py              parse and validate input, shape the JSON response
  │
  ├─ billing/services.py       business logic. No HTTP concepts in here.
  │  projects/…
  │
  └─ models                    TenantScopedQuerySet enforces the tenant predicate
```

Business logic lives in `services.py` modules, not in views. A view's job is to
validate input, call a service, and serialise the result.

## The tenant boundary

Three pieces cooperate:

1. **`tenants/middleware.py`** authenticates the `X-Api-Key` header, attaches
   `request.tenant`, and sets a `ContextVar`. It clears that var in a `finally`
   block — without which a reused worker thread could inherit the previous
   request's tenant, which is a data leak rather than merely a bug.

2. **`tenants/context.py`** holds the current tenant in a `ContextVar` so service
   and model code can reach it without every function signature threading a tenant
   argument through. `tenant_context()` is the escape hatch for management commands
   and tests, which have no middleware.

3. **`tenants/models.py::TenantScopedQuerySet`** provides `.for_current_tenant()`.
   It **fails closed**: with no tenant in context it raises rather than returning
   everything. Any queryset that serves a tenant request must go through it.

> Filtering rows in Python after the query has run is **not** a substitute. The rows
> have already crossed the trust boundary and the database has already scanned
> another tenant's data. Scope in SQL.

`is_internal` tenants exist for support tooling and may legitimately query across
customers. That is the one sanctioned exception, and it must be explicit at the call
site.

## Data model

```
Tenant ──┬── Project ──┐
         │             │
         ├── LineItem ─┘   (project is nullable: not all usage is project-scoped)
         │
         └── Invoice
```

- `LineItem.amount_cents` is an `IntegerField`, not positive-only: credits and
  refunds are negative line items rather than a separate table.
- `Invoice.period_end` is **inclusive**. See the note in `README.md`; this is the
  single easiest thing to get wrong in this codebase.
- Money is integer cents everywhere. No floats.
- `Invoice` has a uniqueness constraint on `(tenant, period_start, period_end)`, so
  re-running the billing job refreshes rather than duplicating.

## Testing

`tests/` runs against real Postgres, inside the app container.

- `tests/test_billing.py` — period arithmetic and invoice totals
- `tests/test_api.py` — endpoint contracts, including the 400/401/403/405 cases
- `tests/test_tenants.py` — the isolation boundary, marked `@pytest.mark.security`

Tests are written to fail for exactly one reason. An assertion on a grand total, for
example, is sensitive to every billing bug there is, so the isolation tests
deliberately assert the *absence of other tenants' rows* instead — a test that fails
for a reason other than its name states sends whoever is debugging the wrong way.

## Deployment

Postgres is Amazon RDS in production. `settings.RDS` carries the instance
identifier, parameter group, IAM-auth flag and read-replica endpoint. Locally a
Postgres container stands in, so RDS-specific behaviour (IAM auth, replica routing,
parameter-group tuning) is configuration only and is not exercised by the suite.
