"""What the generator is allowed to query, and which tables carry a tenant.

**The catalog is the trust boundary.** Everything downstream — the prompt, the policy
rewriter, the executor — decides what to do with a table by asking this module. A table
that is not in here is not queryable, and a table that is in here but is not marked
tenant-scoped is readable by everyone.

That makes :data:`TENANT_SCOPED` the single most security-relevant list in the codebase,
and it is why :func:`is_tenant_scoped` **raises for an unknown table rather than
returning False**. A policy that silently skips what it does not recognise fails open,
and failing open is how a rewriter that looks like it is enforcing something enforces
nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class UnknownTableError(LookupError):
    """Raised for a table the catalog does not know.

    A distinct type because the executor must be able to tell "this question asked for
    something that does not exist" from "this question asked for something it may not
    have", and must never conflate either with "allowed".
    """


@dataclass(frozen=True)
class TableSpec:
    """One queryable table.

    Attributes:
        name: Table name as it appears in SQL.
        tenant_scoped: Whether rows belong to a tenant and the table therefore needs a
            ``tenant_id`` predicate on every reference.
        columns: Column names, used to build the prompt's schema section.
        description: One line for the prompt, so the model picks the right table.
    """

    name: str
    tenant_scoped: bool
    columns: tuple[str, ...]
    description: str = ""
    sample_values: dict[str, tuple[str, ...]] = field(default_factory=dict)


#: Every table the generator may reference. Four of them hold tenant data; ``plans`` is
#: shared reference data and deliberately is not scoped, which is what stops the policy
#: from being a blanket "add tenant_id everywhere" rule that nobody has to think about.
TABLES: dict[str, TableSpec] = {
    "customers": TableSpec(
        name="customers",
        tenant_scoped=True,
        columns=("id", "tenant_id", "name", "email", "country", "created_at"),
        description="People who buy things. One row per customer per tenant.",
    ),
    "orders": TableSpec(
        name="orders",
        tenant_scoped=True,
        columns=("id", "tenant_id", "customer_id", "status", "total_cents", "placed_at"),
        description="Placed orders. total_cents is integer cents, never a float.",
    ),
    "order_items": TableSpec(
        name="order_items",
        tenant_scoped=True,
        columns=("id", "tenant_id", "order_id", "product_id", "quantity", "unit_cents"),
        description="Line items. Join to orders on order_id.",
    ),
    "products": TableSpec(
        name="products",
        tenant_scoped=True,
        columns=("id", "tenant_id", "sku", "name", "category", "price_cents"),
        description="The catalogue each tenant sells from.",
    ),
    "plans": TableSpec(
        name="plans",
        tenant_scoped=False,
        columns=("code", "name", "monthly_cents"),
        description="Shared subscription plans. Reference data, identical for everyone.",
    ),
}

#: Names of the tables that must carry a tenant predicate on every reference.
TENANT_SCOPED: frozenset[str] = frozenset(
    name for name, spec in TABLES.items() if spec.tenant_scoped
)

#: The column every scoped table uses. One name throughout, so the rewriter never has to
#: look up which column a given table happens to use.
TENANT_COLUMN = "tenant_id"


def is_known(table: str) -> bool:
    """Return whether ``table`` is in the catalog at all."""
    return table.lower() in TABLES


def is_tenant_scoped(table: str) -> bool:
    """Return whether ``table`` needs a tenant predicate.

    Args:
        table: Table name, case-insensitive.

    Returns:
        ``True`` if rows in this table belong to a tenant.

    Raises:
        UnknownTableError: If the table is not in the catalog. **Deliberately not
            ``False``.** The caller is a security policy deciding whether to constrain a
            reference, and the only safe answer for something it cannot identify is to
            refuse, not to wave it through.
    """
    spec = TABLES.get(table.lower())
    if spec is None:
        raise UnknownTableError(f"{table!r} is not a known table")
    return spec.tenant_scoped


def schema_prompt_section() -> str:
    """Render the catalog as the schema block of the generation prompt.

    Deterministic ordering, because the prompt text is part of the cassette key: a
    schema section that reorders itself between runs would invalidate every recorded
    response without anything having actually changed.

    Returns:
        A newline-delimited schema description.
    """
    lines: list[str] = []
    for name in sorted(TABLES):
        spec = TABLES[name]
        columns = ", ".join(spec.columns)
        scope = "per-tenant" if spec.tenant_scoped else "shared reference data"
        lines.append(f"{spec.name}({columns})  -- {scope}. {spec.description}")
    return "\n".join(lines)
