-- Row-level security: the second layer, underneath the query rewriter.
--
-- The rewriter in nl2sql/policy/ is the primary defence and this is the backstop. The
-- order matters: RLS is here to catch a mistake in the rewriter, not to excuse one. A
-- query that reaches the database unscoped is already a bug even if RLS stops it.
--
-- Two details that are the entire difference between working RLS and decorative RLS:
--
--   ENABLE turns policies on for everyone except the table's owner.
--   FORCE  turns them on for the owner too.
--
-- Without FORCE, a service that happens to connect as the owner sees every row, and
-- nothing about the schema looks wrong: the policies are present, correctly written,
-- and silently not applied. That failure mode is why FORCE is applied to all four fact
-- tables here rather than being left to the role configuration in the previous
-- migration to get right on its own.
--
-- The policy reads app.tenant_id, a session setting the application sets per
-- transaction with SET LOCAL. current_setting(..., true) returns NULL when it is unset,
-- and `tenant_id = NULL` matches no rows -- so forgetting to set it fails closed, with
-- an empty result rather than a full one.

ALTER TABLE customers    ENABLE ROW LEVEL SECURITY;
ALTER TABLE products     ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders       ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items  ENABLE ROW LEVEL SECURITY;

ALTER TABLE customers    FORCE ROW LEVEL SECURITY;
ALTER TABLE products     FORCE ROW LEVEL SECURITY;
ALTER TABLE orders       FORCE ROW LEVEL SECURITY;
ALTER TABLE order_items  FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON customers;
DROP POLICY IF EXISTS tenant_isolation ON products;
DROP POLICY IF EXISTS tenant_isolation ON orders;
DROP POLICY IF EXISTS tenant_isolation ON order_items;

CREATE POLICY tenant_isolation ON customers
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_isolation ON products
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_isolation ON orders
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_isolation ON order_items
    USING (tenant_id = current_setting('app.tenant_id', true));

-- plans is deliberately absent. It is shared reference data; a policy on it would make
-- the catalogue of subscription plans invisible to everyone.
