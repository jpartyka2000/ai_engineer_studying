-- A reporting view, and a deliberate hole in what the generator may reference.
--
-- v_all_orders exists because the finance export needs a denormalised order line and
-- has needed one since before this service was written. It is used by that export, by
-- hand, over a direct connection.
--
-- It is NOT in nl2sql/catalog.py, and that omission is intentional. A view is a stored
-- query over base tables, and the tenant rewriter cannot see inside it -- adding a
-- predicate to `v_all_orders` constrains the view's output but not the reads the view
-- performs, and whether that is sufficient depends on the view's own text. Rather than
-- reason about that per view, the catalog lists base tables only and the policy refuses
-- anything it cannot resolve to one.
--
-- The adversarial corpus asks for this view by name for exactly that reason.
--
-- Note that the view is declared with security_invoker, so when it IS read directly the
-- reader's own RLS policies apply rather than the view owner's. Without that, a view
-- over an RLS-protected table is a way to launder past the policy.

CREATE OR REPLACE VIEW v_all_orders
WITH (security_invoker = true) AS
SELECT
    o.tenant_id,
    o.id            AS order_id,
    o.status,
    o.total_cents,
    o.placed_at,
    c.name          AS customer_name,
    c.country
FROM orders o
JOIN customers c
  ON c.tenant_id = o.tenant_id
 AND c.id = o.customer_id;

REVOKE ALL ON v_all_orders FROM sqlgenie_app;
