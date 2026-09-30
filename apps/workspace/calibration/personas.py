"""The persona registry: every authored calibration submission, in one place."""

from __future__ import annotations

from apps.workspace.calibration.personas_tenantsaas import (
    EX001_PERSONAS,
    EX002_PERSONAS,
    EX003_PERSONAS,
    EX004_PERSONAS,
    EX005_PERSONAS,
)
from apps.workspace.calibration.spec import Persona, PersonaRegistry

REGISTRY = PersonaRegistry()
REGISTRY.add(
    *EX001_PERSONAS,
    *EX002_PERSONAS,
    *EX003_PERSONAS,
    *EX004_PERSONAS,
    *EX005_PERSONAS,
)


def all_personas() -> list[Persona]:
    """Return every registered persona, in registration order."""
    return list(REGISTRY.personas)


def personas_for(exercise_slug: str) -> list[Persona]:
    """Return the personas authored against one exercise."""
    return REGISTRY.for_exercise(exercise_slug)


def get_persona(key: str) -> Persona:
    """Return one persona by its ``exercise-slug/persona-id`` key.

    Raises:
        KeyError: If no such persona is registered.
    """
    return REGISTRY.get(key)
