"""Persona definitions and the code that replays one into a real workspace.

A persona is a scripted submission: a sequence of commits, each carrying file edits,
plus the NOTES.md the engineer would have written. Replaying one produces a workspace
indistinguishable to the grader from a human attempt -- which is the point, since a
grade obtained any other way would not tell us anything about the real pipeline.

Edits are anchored ``find``/``replace`` pairs rather than patch files. A patch that no
longer applies fails with a rejected hunk somewhere in a temporary directory; an
anchor that no longer matches raises :class:`PersonaError` naming the file and the
string. Since these personas are the calibration corpus and will be replayed against a
template that keeps changing, failing loudly and specifically matters more than
tolerating drift.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from apps.workspace.services import git_ops

logger = logging.getLogger(__name__)

#: Identity every persona commits under. Distinct from the seeded history's authors so
#: ``git log`` makes the submitted work obvious.
CANDIDATE_NAME = "Alex Rivera"
CANDIDATE_EMAIL = "alex.rivera@example.com"


class PersonaError(RuntimeError):
    """A persona could not be replayed into a workspace."""


@dataclass(frozen=True)
class Edit:
    """One file modification inside a commit.

    Exactly one of ``find`` or ``content`` must be set: ``find`` anchors a
    search-and-replace, ``content`` overwrites the whole file.
    """

    path: str
    find: str | None = None
    replace: str = ""
    content: str | None = None
    #: How many times ``find`` is expected to occur. A mismatch raises, because a
    #: persona that silently edits one of two identical call sites is not the
    #: submission it claims to be.
    count: int = 1

    def __post_init__(self) -> None:
        if (self.find is None) == (self.content is None):
            raise ValueError(f"{self.path}: set exactly one of find= or content=")

    def apply_to(self, workspace: Path) -> None:
        """Apply this edit inside a workspace.

        Args:
            workspace: The scaffolded repository root.

        Raises:
            PersonaError: If the file is missing or the anchor does not match the
                expected number of times.
        """
        target = workspace / self.path
        if self.content is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.content, encoding="utf-8")
            return

        if not target.is_file():
            raise PersonaError(f"{self.path} does not exist in the workspace")
        original = target.read_text(encoding="utf-8")
        found = original.count(self.find or "")
        if found != self.count:
            raise PersonaError(
                f"{self.path}: expected {self.count} occurrence(s) of "
                f"{self.find!r}, found {found}. The template has probably changed."
            )
        target.write_text(original.replace(self.find or "", self.replace), encoding="utf-8")


@dataclass(frozen=True)
class Commit:
    """One commit in a persona's history."""

    message: str
    edits: tuple[Edit, ...] = ()
    #: Minutes after the clock started that this commit was made. Only affects the
    #: dates in ``git log``, which the grader reads.
    at_minute: int = 0


@dataclass(frozen=True)
class Persona:
    """A scripted submission at a deliberate quality tier.

    Attributes:
        persona_id: Stable slug, unique within an exercise.
        exercise_slug: The exercise this is a submission to.
        tier: One-line label for the reveal, e.g. "correct fix, no writeup".
        rationale: Why this persona is in the corpus -- what it probes.
        predicted_letter: The letter the *author* of the persona expects a human to
            give. Recorded up front and withheld until the reveal so it cannot be
            rationalised afterwards. It is a third opinion, not the ground truth.
        notes_md: Content for NOTES.md and the in-app notes field. Empty string means
            the engineer left the template untouched.
        commits: The submission's history, in order.
        fraction_time_used: Proportion of the time box consumed before submitting.
        hints_used: Hints revealed during the attempt.
    """

    persona_id: str
    exercise_slug: str
    tier: str
    rationale: str
    predicted_letter: str
    notes_md: str
    commits: tuple[Commit, ...]
    fraction_time_used: float = 0.6
    hints_used: int = 0

    @property
    def key(self) -> str:
        """Globally unique identifier, ``<exercise-slug>/<persona-id>``."""
        return f"{self.exercise_slug}/{self.persona_id}"

    @property
    def writes_notes(self) -> bool:
        """Whether this persona filled in NOTES.md at all."""
        return bool(self.notes_md.strip())


#: Filenames a persona is never allowed to touch, whatever its edits say. Protected
#: paths are per-exercise, but a persona editing the harness sentinel would corrupt
#: the workspace itself rather than merely score badly.
FORBIDDEN_EDIT_PREFIXES = (".git/", ".ai-prep-workspace", ".grading/")


def _commit_env(when) -> dict[str, str]:
    """Build the git environment attributing a commit to the candidate."""
    stamp = when.isoformat()
    return {
        "GIT_AUTHOR_NAME": CANDIDATE_NAME,
        "GIT_AUTHOR_EMAIL": CANDIDATE_EMAIL,
        "GIT_AUTHOR_DATE": stamp,
        "GIT_COMMITTER_NAME": CANDIDATE_NAME,
        "GIT_COMMITTER_EMAIL": CANDIDATE_EMAIL,
        "GIT_COMMITTER_DATE": stamp,
    }


def apply_persona(workspace: Path, persona: Persona, *, started_at) -> list[str]:
    """Replay a persona's submission into a scaffolded workspace.

    A persona that fills in NOTES.md normally scripts the commit that does so, which is
    what puts *when* they wrote it into the history the grader reads. If it supplies
    notes without ever committing them, they are written before the first commit rather
    than left in a dirty tree -- a stray uncommitted NOTES.md would trip the
    "no commits" engineering deduction for a reason the persona never intended.

    Args:
        workspace: The scaffolded repository root.
        persona: The persona to replay.
        started_at: When the session's clock started; commit dates are offset from it.

    Returns:
        The SHA of each commit created, in order.

    Raises:
        PersonaError: If an edit does not apply, or a commit produces no change.
    """
    notes_committed = False
    for commit in persona.commits:
        for edit in commit.edits:
            if edit.path.startswith(FORBIDDEN_EDIT_PREFIXES):
                raise PersonaError(f"{persona.key}: refusing to edit {edit.path}")
            if edit.path == "NOTES.md":
                notes_committed = True

    if persona.writes_notes and not notes_committed:
        (workspace / "NOTES.md").write_text(persona.notes_md, encoding="utf-8")

    shas: list[str] = []
    for index, commit in enumerate(persona.commits):
        for edit in commit.edits:
            edit.apply_to(workspace)

        git_ops.run_git(workspace, "add", "-A")
        staged = git_ops.run_git(workspace, "diff", "--cached", "--name-only")
        if not staged.strip():
            raise PersonaError(
                f"{persona.key}: commit {index + 1} ({commit.message.splitlines()[0]!r}) "
                "changed nothing. Its edits are probably already satisfied."
            )
        when = started_at + timedelta(minutes=commit.at_minute)
        git_ops.run_git(
            workspace, "commit", "-q", "-m", commit.message, env_extra=_commit_env(when)
        )
        shas.append(git_ops.head_sha(workspace))
        logger.info("persona %s commit %d: %s", persona.key, index + 1, staged.replace("\n", " "))

    return shas


@dataclass
class PersonaRegistry:
    """Lookup over every authored persona."""

    personas: list[Persona] = field(default_factory=list)

    def add(self, *personas: Persona) -> None:
        """Register personas, rejecting duplicate keys."""
        existing = {persona.key for persona in self.personas}
        for persona in personas:
            if persona.key in existing:
                raise ValueError(f"duplicate persona {persona.key}")
            existing.add(persona.key)
            self.personas.append(persona)

    def for_exercise(self, exercise_slug: str) -> list[Persona]:
        """Return every persona authored against one exercise."""
        return [p for p in self.personas if p.exercise_slug == exercise_slug]

    def get(self, key: str) -> Persona:
        """Return one persona by its ``exercise-slug/persona-id`` key.

        Raises:
            KeyError: If no such persona is registered.
        """
        for persona in self.personas:
            if persona.key == key:
                return persona
        raise KeyError(key)

    @property
    def exercise_slugs(self) -> list[str]:
        """Every exercise with at least one persona, in registration order."""
        seen: list[str] = []
        for persona in self.personas:
            if persona.exercise_slug not in seen:
                seen.append(persona.exercise_slug)
        return seen
