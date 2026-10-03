-- Tenants and the keys that identify them.
--
-- A tenant is the isolation boundary for everything else in this schema. The table
-- itself is deliberately NOT tenant-scoped: it is the thing tenants are rows of, and
-- scoping it to itself is a circularity that helps nobody.
--
-- api_keys stores a hash, never the key. The service compares hashes, so a dump of this
-- table does not hand anybody a working credential.

CREATE TABLE IF NOT EXISTS tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    plan_code   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_sha256  TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id),
    label       TEXT NOT NULL,
    revoked_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lookup is by hash on every single request, so it is the one index that is not
-- optional. A sequential scan here would be a per-request scan of every key we have
-- ever issued.
CREATE INDEX IF NOT EXISTS api_keys_tenant_idx ON api_keys (tenant_id);
