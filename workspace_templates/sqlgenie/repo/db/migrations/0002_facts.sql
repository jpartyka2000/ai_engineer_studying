-- The four tenant-scoped fact tables.
--
-- Every one carries tenant_id as a real column rather than relying on a join to infer
-- ownership. The redundancy is the point: order_items could reach its tenant through
-- orders, but then a query that touches order_items alone would have nothing to filter
-- on, and the rewriter would have to understand joins to scope it. A denormalised
-- tenant_id means every table can be constrained in isolation.
--
-- Money is integer cents throughout. Never a float, never a numeric that somebody will
-- eventually divide in SQL and round differently from the application.

CREATE TABLE IF NOT EXISTS customers (
    id          BIGINT NOT NULL,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id),
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    country     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS products (
    id          BIGINT NOT NULL,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id),
    sku         TEXT NOT NULL,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    price_cents BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS orders (
    id           BIGINT NOT NULL,
    tenant_id    TEXT NOT NULL REFERENCES tenants(id),
    customer_id  BIGINT NOT NULL,
    status       TEXT NOT NULL,
    total_cents  BIGINT NOT NULL,
    placed_at    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, customer_id) REFERENCES customers (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id          BIGINT NOT NULL,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id),
    order_id    BIGINT NOT NULL,
    product_id  BIGINT NOT NULL,
    quantity    INTEGER NOT NULL,
    unit_cents  BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, order_id) REFERENCES orders (tenant_id, id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES products (tenant_id, id)
);

-- The composite primary keys lead with tenant_id, so every lookup by tenant is an index
-- range rather than a filter applied after the fact.
CREATE INDEX IF NOT EXISTS orders_tenant_placed_idx ON orders (tenant_id, placed_at DESC);
CREATE INDEX IF NOT EXISTS order_items_tenant_order_idx ON order_items (tenant_id, order_id);
