-- Shared reference data.
--
-- plans is readable by everyone and belongs to nobody. It exists so that the tenant
-- policy has something to *not* constrain: a rewriter that adds tenant_id to every
-- table it sees is not enforcing a rule, it is applying a reflex, and the difference
-- only shows up on a table like this one.
--
-- It is also why the adversarial corpus has a legitimately cross-tenant question. A
-- policy that refuses everything passes every attack case and fails that one.

CREATE TABLE IF NOT EXISTS plans (
    code          TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    monthly_cents BIGINT NOT NULL
);

INSERT INTO plans (code, name, monthly_cents) VALUES
    ('starter',    'Starter',    4900),
    ('growth',     'Growth',    19900),
    ('enterprise', 'Enterprise', 99900)
ON CONFLICT (code) DO NOTHING;
