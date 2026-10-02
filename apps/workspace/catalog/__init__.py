"""The authored exercise catalog.

One module per base application, each exposing an ``EXERCISES`` list of dicts --
following the precedent set by
``apps/systemdesign/management/commands/seed_systemdesign_challenges.py``, where
content is authored as plain data and loaded by a management command.

Every entry is validated against
:class:`~apps.workspace.schemas.AuthoredExercise` at seed time, so a malformed
exercise fails loudly instead of reaching the database.
"""

from apps.workspace.catalog import edakit, etlduck, eventstore, predictsvc, tenantsaas

#: Every authored exercise, in catalog order.
EXERCISES: list[dict] = [
    *tenantsaas.EXERCISES,
    *predictsvc.EXERCISES,
    *edakit.EXERCISES,
    *etlduck.EXERCISES,
    *eventstore.EXERCISES,
]

__all__ = ["EXERCISES"]
