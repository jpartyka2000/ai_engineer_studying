"""Tests for grading-prompt assembly, focused on the writeup section.

The prompt is what the model scores, so anything that changes how much of a submission
appears in it changes grades. The duplicate-writeup collapse is the case with teeth: an
engineer who fills the notes panel *and* commits NOTES.md would otherwise have their
prose printed twice, and length is one of the few proxies for effort a reader has.
"""

from types import SimpleNamespace

import pytest

from apps.workspace.services.check_runner import CheckRunSummary
from apps.workspace.services.prompt_budget import (
    MIN_DUPLICATE_CHARS,
    _is_same_writeup,
    build_grading_prompt,
)

WRITEUP = (
    "## Diagnosis\n\nThe period filter drops the final day because created_at is a "
    "timestamp while the bounds are dates, so the database coerces each bound to "
    "midnight and the exclusive upper bound excludes the whole closing day.\n\n"
    "## The fix\n\nCompare dates to dates with created_at__date__gte and "
    "created_at__date__lte, which states the inclusive rule in the query itself.\n"
)

TEMPLATE = (
    "# Engineering notes\n\nFill this in as you work.\n\n## Diagnosis\n\n"
    "<!-- What is the observable symptom? -->\n\n## The fix\n\n<!-- What you changed -->\n"
)


def build(*, notes: str, full_files: dict[str, str]) -> str:
    """Assemble a prompt from the smallest stand-ins the builder actually touches."""
    exercise = SimpleNamespace(
        title="A ticket",
        get_exercise_type_display=lambda: "Critical bug",
        difficulty="intermediate",
        expected_time_minutes=19,
        brief_md="The brief.",
        definition_of_done=["R1: something"],
        grading_notes="Private notes.",
        focus_paths=["billing/services.py"],
        context_excerpts=[],
        grading_spec={"checks": []},
        hints=["a hint"],
    )
    session = SimpleNamespace(
        elapsed_seconds=17 * 60,
        time_limit_seconds=30 * 60,
        end_reason="submitted",
        EndReason=SimpleNamespace(TIMED_OUT="timed_out"),
        hints_used=0,
        user_notes=notes,
    )
    submission = SimpleNamespace(
        diff_numstat=[{"path": "billing/services.py", "added": 2, "deleted": 2, "status": "M"}],
        capture_ok=True,
        capture_error="",
        full_files=full_files,
        git_log="abc1234 Dev Mon Jan 1 00:00:00 2026 +0000\nfix period filter\n",
        diff_text="--- a/billing/services.py\n+++ b/billing/services.py\n+x\n-y\n",
        files_changed=1,
        lines_added=2,
        lines_deleted=2,
        user_commit_count=1,
    )
    return build_grading_prompt(
        exercise=exercise, session=session, submission=submission, check_summary=CheckRunSummary()
    ).text


# ---------------------------------------------------------------------------
# _is_same_writeup
# ---------------------------------------------------------------------------


def test_identical_prose_is_the_same_writeup():
    assert _is_same_writeup(WRITEUP, WRITEUP) is True


def test_formatting_differences_do_not_defeat_the_match():
    reflowed = WRITEUP.replace("\n\n", "\n").replace(" so the", "  SO the")
    assert _is_same_writeup(reflowed, WRITEUP) is True


def test_a_trailing_edit_in_one_copy_still_matches():
    assert _is_same_writeup(WRITEUP + "\n## Risks\n\nLow.\n", WRITEUP) is True


def test_different_prose_is_not_the_same_writeup():
    assert _is_same_writeup(TEMPLATE, WRITEUP) is False


def test_an_empty_side_never_matches():
    """An unfilled template alongside an empty notes field is not a duplicate."""
    assert _is_same_writeup(TEMPLATE, "") is False
    assert _is_same_writeup("", WRITEUP) is False


def test_a_short_shared_sentence_is_not_a_duplicate():
    """Containment alone is not enough -- losing evidence is worse than a near-duplicate."""
    shared = "Fixed the period filter."
    assert len(shared) < MIN_DUPLICATE_CHARS
    assert _is_same_writeup(shared, f"{WRITEUP}\n{shared}") is False


# ---------------------------------------------------------------------------
# The assembled prompt
# ---------------------------------------------------------------------------


def test_a_writeup_submitted_twice_is_printed_once():
    text = build(notes=WRITEUP, full_files={"NOTES.md": WRITEUP})
    assert text.count("Compare dates to dates") == 1
    assert "shown once" in text
    assert "NOTES.md" in text


def test_the_surviving_copy_is_the_longer_one():
    """A trailing edit made in the file but not the panel must not be lost."""
    longer = WRITEUP + "\n## Risks and follow-ups\n\nNo application code changed.\n"
    text = build(notes=WRITEUP, full_files={"NOTES.md": longer})
    assert "No application code changed." in text
    assert text.count("Compare dates to dates") == 1


def test_a_different_markdown_file_is_still_printed():
    text = build(notes=WRITEUP, full_files={"NOTES.md": WRITEUP, "ARCHITECTURE.md": TEMPLATE})
    assert "## ARCHITECTURE.md" in text
    assert text.count("Compare dates to dates") == 1


def test_an_empty_notes_field_with_an_unfilled_template_is_unchanged():
    """The prompt for a submission with no writeup must not shift.

    Five calibration submissions are in exactly this state, and their recorded grades
    stay comparable only while their prompt is byte-identical.
    """
    text = build(notes="", full_files={"NOTES.md": TEMPLATE})
    assert "(the engineer left this empty)" in text
    assert "shown once" not in text
    assert "## NOTES.md" in text
    assert "What is the observable symptom?" in text


def test_a_writeup_in_only_one_place_is_printed_once_without_a_provenance_note():
    panel_only = build(notes=WRITEUP, full_files={})
    assert panel_only.count("Compare dates to dates") == 1
    assert "shown once" not in panel_only

    file_only = build(notes="", full_files={"NOTES.md": WRITEUP})
    assert file_only.count("Compare dates to dates") == 1
    assert "shown once" not in file_only
    assert "(the engineer left this empty)" in file_only


@pytest.mark.parametrize("notes", ["", WRITEUP])
def test_the_writeup_section_is_always_present(notes):
    assert "# NOTES.md AS SUBMITTED" in build(notes=notes, full_files={})
