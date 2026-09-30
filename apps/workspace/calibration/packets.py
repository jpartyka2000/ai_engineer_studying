"""Render the blind grading packet for one graded item.

The packet body is the **verbatim grading prompt** the model was sent, rebuilt from the
stored submission rather than paraphrased. That is the whole design: any summary would
introduce a difference between what the human judged and what the model judged, and
then a disagreement could not be attributed to the rubric. Truncation included -- if
the diff was trimmed before the model saw it, the human grades the trimmed diff too.

What the packet deliberately omits is the system's verdict: no letter, no dimension
scores, no feedback, and no persona label. The item id is a hash, so it leaks no tier
or ordering either.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.workspace.calibration import store
from apps.workspace.models import WorkspaceSession
from apps.workspace.services.check_runner import CheckRunSummary, CheckOutcome
from apps.workspace.services.prompt_budget import build_grading_prompt

HEADER = """\
# {item}

A time-boxed change to a production codebase, for you to grade by hand. Everything
below is the exact evidence the automated grader was given, in the order it was given
it -- brief, definition of done, private grading notes, acceptance check results, the
commit log, and the diff.

Grade it as you would a colleague's pull request. Record your letter in
`scoresheet.md` under `## {item}` before looking at anything else.

Weights: correctness 40, engineering quality 25, documentation 25, completeness 10.
Calibration anchors: 70 is a competent junior, 85 solid mid-level, 95+ is what a staff
engineer would ship.

---

"""


@dataclass
class Packet:
    """A rendered blind packet."""

    item: str
    session_id: int
    text: str

    @property
    def char_count(self) -> int:
        """Size of the packet, for reporting."""
        return len(self.text)


def _summary_from_db(session: WorkspaceSession) -> CheckRunSummary:
    """Rebuild a check summary from the persisted check results.

    Re-deriving it from the database rather than re-running the checks keeps packet
    generation instant and offline, and guarantees the packet shows the results that
    actually fed the grade rather than a fresh run that might differ.

    Args:
        session: A graded session with a captured submission.

    Returns:
        A :class:`CheckRunSummary` equivalent to the one grading used.
    """
    submission = session.submission
    summary = CheckRunSummary(
        outcomes=[
            CheckOutcome(
                check_id=row.check_id,
                kind=row.kind,
                status=row.status,
                passed=row.passed,
                weight=row.weight,
                required=row.required,
                stretch=row.stretch,
                expected=row.expected,
                actual=row.actual,
                description=row.description,
                duration_ms=row.duration_ms,
                output=row.output,
            )
            for row in submission.check_results.all()
        ],
    )
    grade = getattr(session, "grade", None)
    if grade:
        # Regressions and tampering are not stored per check, but the grade records
        # the caps they produced, which is what the prompt reports.
        summary.tampered_paths = (
            ["(a protected file was modified)"]
            if "G4_test_tampering" in (grade.applied_caps or [])
            else []
        )
        summary.regressions = (
            ["(at least one previously-passing test broke)"]
            if "G3_regression" in (grade.applied_caps or [])
            else []
        )
    return summary


def render(session: WorkspaceSession, persona_key: str) -> Packet:
    """Render the blind packet for one graded session.

    Args:
        session: A session that has been captured and graded.
        persona_key: The persona behind it, used only to derive the opaque item id.

    Returns:
        The rendered :class:`Packet`.

    Raises:
        ValueError: If the session has no captured submission to render.
    """
    if not hasattr(session, "submission"):
        raise ValueError(f"session {session.pk} has no captured submission")

    item = store.item_id(persona_key)
    built = build_grading_prompt(
        exercise=session.exercise,
        session=session,
        submission=session.submission,
        check_summary=_summary_from_db(session),
    )
    return Packet(
        item=item,
        session_id=session.pk,
        text=HEADER.format(item=item) + built.text + "\n",
    )


def write(packet: Packet) -> str:
    """Write a packet to the packets directory.

    Args:
        packet: The packet to write.

    Returns:
        The path written, as a string.
    """
    directory = store.packets_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{packet.item}.md"
    path.write_text(packet.text, encoding="utf-8")
    return str(path)
