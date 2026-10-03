"""sqlgenie: natural-language questions answered against multi-tenant Postgres.

A question comes in as English, a recorded model turns it into SQL, and that SQL is
rewritten to constrain every read to the asking tenant before it runs. The rewrite is
the security boundary; row-level security in the database is the second layer under it.

Two things are worth knowing before changing anything:

**The model is not a security control.** The prompt asks for tenant-scoped SQL and
asking is all it does. Everything that enforces isolation lives in
:mod:`sqlgenie.nl2sql.policy` and in ``db/migrations/0005_row_level_security.sql``.

**There is no live model and no network call.** Generations are recorded in
``fixtures/llm_cassettes/`` and looked up by a hash of the exact request. A miss is an
error, never a fallback.

Read ``ARCHITECTURE.md`` for why the rewrite walks query scopes rather than tables, and
why both tenants in the development data are deliberately identical.
"""

from __future__ import annotations

__version__ = "0.6.0"

__all__ = ["__version__"]
