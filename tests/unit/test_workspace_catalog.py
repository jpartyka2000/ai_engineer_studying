"""Static checks over the authored exercise catalog.

These are the cheap half of exercise verification: everything that can be decided by
reading the catalog and the patch files, with no container, no database and no clock.
The expensive half -- does the mutation actually fail in the authored way, does
``reference.patch`` actually solve it -- lives in the ``verify_workspace_exercises``
management command, because it needs a real workspace.

The most important test here is the answer-leak check. A hint that quietly contains the
fix, or a brief that does, is invisible on review and ruins the exercise permanently.
"""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

# The package aggregate, not one base app's module. Imported from a single base app
# these checks silently stop covering every exercise authored on the next one -- which
# is exactly what happened when predictsvc was added and all 18 kept passing.
from apps.workspace.catalog import EXERCISES
from apps.workspace.schemas import AuthoredExercise
from apps.workspace.services import manifest, paths

#: Minimum length of a code fragment before it is distinctive enough that finding it in
#: a brief means the answer leaked. Short lines (`)`, `return`, `items = ...`) appear in
#: unrelated code constantly and would only produce false alarms.
DISTINCTIVE_LENGTH = 24


@pytest.fixture(scope="module")
def authored() -> list[AuthoredExercise]:
    """Every authored exercise, validated."""
    return [AuthoredExercise.model_validate(entry) for entry in EXERCISES]


def patch_dir(slug: str) -> Path:
    """Return the directory holding one exercise's patches."""
    return paths.template_root() / manifest.PATCHES_DIRNAME / slug


def added_code_lines(patch_text: str) -> list[str]:
    """Return the code lines a patch adds, excluding prose.

    Comments and docstring text are skipped: a reference patch restores the comment
    explaining the invariant, and a brief legitimately explains the same invariant in
    the same words. Overlapping prose is expected; overlapping *code* is a leak.
    """
    lines = []
    for raw in patch_text.splitlines():
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        body = raw[1:].strip()
        if not body or body.startswith(("#", '"""', "'''", "*", "-")):
            continue
        lines.append(body)
    return lines


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_every_entry_validates():
    """A malformed entry must fail here rather than at seed time."""
    for entry in EXERCISES:
        try:
            AuthoredExercise.model_validate(entry)
        except ValidationError as exc:
            pytest.fail(f"{entry.get('slug')}: {exc}")


def test_slugs_and_numbers_are_unique(authored):
    slugs = [exercise.slug for exercise in authored]
    numbers = [exercise.exercise_number for exercise in authored]
    assert len(set(slugs)) == len(slugs)
    assert len(set(numbers)) == len(numbers)


def test_slug_matches_its_exercise_number(authored):
    for exercise in authored:
        assert exercise.slug.startswith(f"ex-{exercise.exercise_number:03d}-"), exercise.slug


def test_expected_time_leaves_room_for_the_writeup(authored):
    """The slack between the estimate and the limit is where NOTES.md gets written.

    The plan puts the estimate at 60-70% of the limit and says so in every brief, so an
    estimate at 90% of the box would make the documentation weight unfair.
    """
    for exercise in authored:
        ratio = exercise.expected_time_minutes / exercise.time_limit_minutes
        assert 0.45 <= ratio <= 0.75, f"{exercise.slug}: estimate is {ratio:.0%} of the limit"


# ---------------------------------------------------------------------------
# Variety
# ---------------------------------------------------------------------------


def test_defect_class_is_never_reused_within_a_base_app(authored):
    """The plan's strongest variety rule: never twice within one base app.

    Text similarity is weak -- two exercises can read completely differently and teach
    the same lesson -- so the closed defect-class vocabulary is what actually guarantees
    variety.
    """
    seen: dict[tuple[str, str], str] = {}
    for exercise in authored:
        key = (exercise.base_app, exercise.defect_class)
        assert key not in seen, (
            f"{exercise.slug} reuses defect_class {exercise.defect_class!r} on "
            f"{exercise.base_app}, already used by {seen[key]}"
        )
        seen[key] = exercise.slug


def test_titles_are_not_near_duplicates(authored):
    """Flag titles that read as the same ticket."""
    from difflib import SequenceMatcher

    for index, left in enumerate(authored):
        for right in authored[index + 1 :]:
            ratio = SequenceMatcher(None, left.title, right.title).ratio()
            assert ratio <= 0.55, f"{left.slug} and {right.slug} titles are {ratio:.0%} similar"


# ---------------------------------------------------------------------------
# Checks and paths
# ---------------------------------------------------------------------------


def test_every_exercise_has_at_least_one_required_check(authored):
    for exercise in authored:
        assert any(check.required for check in exercise.checks), exercise.slug


def test_check_ids_are_unique_within_an_exercise(authored):
    for exercise in authored:
        ids = [check.id for check in exercise.checks]
        assert len(set(ids)) == len(ids), exercise.slug


def test_stretch_checks_are_never_required(authored):
    """A required stretch goal is a contradiction: stretch means optional."""
    for exercise in authored:
        for check in exercise.checks:
            assert not (check.stretch and check.required), f"{exercise.slug}:{check.id}"


def test_protected_paths_are_covered_by_a_file_unchanged_check(authored):
    """Declaring a path protected does nothing unless a check hashes it."""
    for exercise in authored:
        if not exercise.protected_paths:
            continue
        hashed = {
            path
            for check in exercise.checks
            if check.kind == "file_unchanged"
            for path in check.paths
        }
        missing = set(exercise.protected_paths) - hashed
        assert not missing, f"{exercise.slug}: {missing} protected but never hashed"


def test_focus_paths_exist_in_the_template(authored):
    for exercise in authored:
        repo = manifest.repo_dir(exercise.base_app)
        for rel in exercise.focus_paths:
            assert (repo / rel).exists(), f"{exercise.slug}: focus path {rel} does not exist"


def test_context_excerpt_paths_exist_in_the_template(authored):
    for exercise in authored:
        repo = manifest.repo_dir(exercise.base_app)
        for excerpt in exercise.context_excerpts:
            assert (repo / excerpt.path).exists(), f"{exercise.slug}: {excerpt.path} missing"


# ---------------------------------------------------------------------------
# Patches
# ---------------------------------------------------------------------------


def test_every_exercise_ships_a_reference_patch(authored):
    """Non-negotiable: without one you cannot prove the exercise is solvable."""
    for exercise in authored:
        assert (patch_dir(exercise.slug) / "reference.patch").is_file(), exercise.slug


def test_every_declared_mutation_patch_exists(authored):
    for exercise in authored:
        for step in exercise.mutations:
            assert step.get("op") == "apply_patch", f"{exercise.slug}: {step}"
            assert (patch_dir(exercise.slug) / step["patch"]).is_file(), exercise.slug


def test_the_reference_patch_reverses_the_mutation(authored):
    """The two patches must be inverses, or the reference does not restore the template.

    Compared as sorted multisets of changed lines: the reference's additions must be the
    mutation's removals and vice versa. Cheaper than applying both, and it catches a
    reference patch that was edited without regenerating its pair.
    """
    for exercise in authored:
        if not exercise.mutations:
            continue
        directory = patch_dir(exercise.slug)
        mutation = (directory / "mutation.patch").read_text(encoding="utf-8")
        reference = (directory / "reference.patch").read_text(encoding="utf-8")

        def changes(text: str) -> tuple[list[str], list[str]]:
            added = sorted(
                line[1:] for line in text.splitlines() if line.startswith("+") and line[:3] != "+++"
            )
            removed = sorted(
                line[1:] for line in text.splitlines() if line.startswith("-") and line[:3] != "---"
            )
            return added, removed

        mutation_added, mutation_removed = changes(mutation)
        reference_added, reference_removed = changes(reference)
        assert mutation_added == reference_removed, exercise.slug
        assert mutation_removed == reference_added, exercise.slug


def test_the_answer_does_not_leak_into_the_brief_or_hints(authored):
    """No distinctive line of the fix may appear in anything the candidate is shown.

    This is the check that cannot be done by review: a hint written weeks after the
    patch is exactly where the fix gets quietly pasted, and nobody notices until the
    exercise has been solved by reading.
    """
    for exercise in authored:
        reference = patch_dir(exercise.slug) / "reference.patch"
        if not reference.is_file():
            continue
        visible = "\n".join([exercise.brief_md, *exercise.hints, *exercise.definition_of_done])
        for line in added_code_lines(reference.read_text(encoding="utf-8")):
            if len(line) < DISTINCTIVE_LENGTH:
                continue
            assert line not in visible, (
                f"{exercise.slug}: the brief or a hint contains a line of the fix "
                f"verbatim: {line!r}"
            )


def test_grading_notes_are_authored_for_every_exercise(authored):
    """The grader is sent these verbatim; an empty one means grading on vibes."""
    for exercise in authored:
        assert len(exercise.grading_notes) > 400, exercise.slug


def test_the_brief_never_contains_a_grading_note(authored):
    """Grading notes are private. Leaking one hands over the watch-for list."""
    for exercise in authored:
        for paragraph in re.split(r"\n\s*\n", exercise.grading_notes):
            stripped = paragraph.strip()
            if len(stripped) > 80:
                assert stripped not in exercise.brief_md, exercise.slug
