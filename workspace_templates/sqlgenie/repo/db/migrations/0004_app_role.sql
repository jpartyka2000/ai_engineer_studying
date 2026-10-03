-- The role the application connects as.
--
-- Separate from the owner, and that separation is load-bearing rather than hygiene.
-- PostgreSQL exempts a table's owner from its row-level security policies unless the
-- table is declared FORCE ROW LEVEL SECURITY. A service that connects as the owner of
-- the tables it queries therefore has RLS enabled and inert -- the policies exist, they
-- are listed by \d, and they filter nothing.
--
-- So: migrations run as the owner, the application runs as sqlgenie_app, and
-- sqlgenie_app owns nothing. The next migration adds FORCE as well, because defending
-- this with one mechanism when two are available is a choice nobody could justify after
-- an incident.
--
-- SELECT only. This service answers questions; it has no business writing, and a
-- generated statement that tried to would fail at the database as well as at the policy.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sqlgenie_app') THEN
        CREATE ROLE sqlgenie_app LOGIN PASSWORD 'app';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE sqlgenie TO sqlgenie_app;
GRANT USAGE ON SCHEMA public TO sqlgenie_app;

GRANT SELECT ON customers, products, orders, order_items, plans TO sqlgenie_app;

-- Explicitly withheld. api_keys is read by the authentication path using the owner
-- connection; the query-answering role must not be able to enumerate credentials even
-- if a generated statement somehow named the table.
REVOKE ALL ON api_keys FROM sqlgenie_app;
REVOKE ALL ON tenants FROM sqlgenie_app;
