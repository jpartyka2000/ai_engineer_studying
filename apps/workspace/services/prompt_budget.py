"""Assemble the grading prompt within a character budget.

A submission is a multi-file diff plus prose plus test output, which can easily
exceed what is sensible to send. Sections are therefore assembled in priority
order and trimmed from the bottom up:

* **P0** metadata, brief, definition of done, private grading notes, the complete
  check-results table, and a one-line summary of **every** changed file. Never cut.
* **P1** ``NOTES.md`` and any changed Markdown. Never cut -- prose cannot be scored
  if it was not read.
* **P2** commit log with full bodies.
* **P3** the unified diff, ordered by relevance rather than alphabetically.
* **P4** authored excerpts of unchanged code needed to judge fit with the codebase.
* **P5** raw test output. First to go.

Every elision emits an explicit marker so the model knows it saw a partial view and
can hedge rather than confidently mis-scoring. Budgeting is in characters at roughly
3.5 chars per token, which avoids adding a tokenizer dependency.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from django.conf import settings

from apps.workspace.services.check_runner import CheckRunSummary
from apps.workspace.services.diff_collector import FileChange, relevance_order

logger = logging.getLogger(__name__)

#: Rough characters per token. Used only to translate a token intuition into the
#: character budget actually enforced.
CHARS_PER_TOKEN = 3.5

_WHITESPACE = re.compile(r"\s+")

#: A duplicate is only collapsed when the shorter copy is at least this long. Two short
#: files that happen to share a sentence are not the same writeup, and dropping one
#: would lose evidence.
MIN_DUPLICATE_CHARS = 200


def _normalise_prose(text: str) -> str:
    """Reduce prose to a form where formatting differences do not matter."""
    return _WHITESPACE.sub(" ", text or "").strip().lower()


def _is_same_writeup(candidate: str, notes: str) -> bool:
    """Whether a Markdown file carries the same writeup as the notes field.

    Deliberately conservative: exact match after normalisation, or one side wholly
    containing the other with the shorter side substantial. A similarity ratio would
    also catch a file that was edited in one place and not the other, but it would
    sometimes drop a file saying something genuinely different -- and losing evidence is
    worse than printing a near-duplicate.
    """
    left, right = _normalise_prose(candidate), _normalise_prose(notes)
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= MIN_DUPLICATE_CHARS and shorter in longer


@dataclass
class BuiltPrompt:
    """An assembled grading prompt plus an account of what was left out."""

    text: str = ""
    sections_truncated: list[str] = field(default_factory=list)
    omitted_files: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        """Length of the assembled prompt in characters."""
        return len(self.text)

    @property
    def approx_tokens(self) -> int:
        """Rough token estimate, for logging and cost awareness."""
        return int(self.char_count / CHARS_PER_TOKEN)

    @property
    def truncated(self) -> bool:
        """Whether anything had to be dropped or elided."""
        return bool(self.sections_truncated)


def _elide(text: str, limit: int, *, label: str) -> tuple[str, bool]:
    """Trim a block, keeping the head and tail and marking the gap.

    Keeps 60% from the start and 20% from the end: a diff's opening hunks carry the
    substance, while the tail is where a stray debugging line tends to be left
    behind.

    Args:
        text: The block to trim.
        limit: Maximum characters.
        label: Used in the elision marker.

    Returns:
        ``(text, was_elided)``.
    """
    if len(text) <= limit:
        return text, False
    head_size = int(limit * 0.6)
    tail_size = int(limit * 0.2)
    head = text[:head_size]
    tail = text[-tail_size:] if tail_size else ""
    omitted = len(text) - head_size - tail_size
    marker = f"\n\n... [{omitted} characters of {label} omitted for length] ...\n\n"
    return head + marker + tail, True


def _numstat_table(changes: list[FileChange]) -> str:
    """Render the complete inventory of changed files.

    Always included in full, even when the diff itself is trimmed, so the grader can
    never mistake a trimmed view for the whole change.
    """
    if not changes:
        return "(no files changed)"
    lines = ["| file | +added | -deleted |", "|---|---|---|"]
    lines += [f"| {c.path} | {c.added} | {c.deleted} |" for c in changes]
    return "\n".join(lines)


def _checks_table(summary: CheckRunSummary) -> str:
    """Render the objective check results, which are authoritative on correctness."""
    if not summary.outcomes:
        return "(no automated checks were run)"
    lines = [
        "| check | kind | required | result | expected | actual |",
        "|---|---|---|---|---|---|",
    ]
    for outcome in summary.outcomes:
        role = "required" if outcome.required else ("stretch" if outcome.stretch else "optional")
        lines.append(
            f"| {outcome.check_id} | {outcome.kind} | {role} | "
            f"**{outcome.status.upper()}** | {outcome.expected or '-'} | {outcome.actual or '-'} |"
        )
    return "\n".join(lines)


def _diff_section(
    diff_text: str,
    changes: list[FileChange],
    *,
    focus_paths: list[str],
    check_paths: list[str],
    budget: int,
    per_file_limit: int,
    report: BuiltPrompt,
) -> str:
    """Render the unified diff, trimming the least relevant files first.

    Split per file and reassembled in relevance order, so trimming drops the file
    least likely to matter rather than whichever happens to sort last.
    """
    if not diff_text:
        return "(no textual changes)"

    # Split the combined diff into per-file chunks keyed by path.
    chunks: dict[str, str] = {}
    current_path = ""
    buffer: list[str] = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_path:
                chunks[current_path] = "".join(buffer)
            buffer = [line]
            # "diff --git a/x b/x" -> take the b-side path.
            parts = line.split()
            current_path = parts[-1][2:] if len(parts) >= 4 else parts[-1]
        else:
            buffer.append(line)
    if current_path:
        chunks[current_path] = "".join(buffer)
    if not chunks:
        chunks = {"(diff)": diff_text}

    ordered_paths = [
        change.path
        for change in relevance_order(changes, focus_paths=focus_paths, check_paths=check_paths)
        if change.path in chunks
    ]
    # Any chunk the numstat did not mention still gets emitted, just last.
    ordered_paths += [path for path in chunks if path not in ordered_paths]

    pieces: list[str] = []
    used = 0
    for path in ordered_paths:
        chunk = chunks[path]
        trimmed, elided = _elide(chunk, per_file_limit, label=f"the diff of {path}")
        if elided:
            report.sections_truncated.append(f"diff:{path}")
        if used + len(trimmed) > budget:
            report.omitted_files.append(path)
            continue
        pieces.append(trimmed)
        used += len(trimmed)

    if report.omitted_files:
        report.sections_truncated.append("diff:dropped-files")
        pieces.append(
            "\n... [the diffs of these files were omitted for length; their line "
            "counts are in the changed-files table above: "
            + ", ".join(report.omitted_files)
            + "] ...\n"
        )
    return "".join(pieces)


def build_grading_prompt(
    *,
    exercise,
    session,
    submission,
    check_summary: CheckRunSummary,
    max_chars: int | None = None,
) -> BuiltPrompt:
    """Assemble the grading prompt for one submission.

    Args:
        exercise: The :class:`~apps.workspace.models.WorkspaceExercise`.
        session: The :class:`~apps.workspace.models.WorkspaceSession`.
        submission: The :class:`~apps.workspace.models.WorkspaceSubmission`.
        check_summary: Results of the objective checks.
        max_chars: Budget override; defaults to ``WORKSPACE_MAX_DIFF_CHARS``.

    Returns:
        A :class:`BuiltPrompt`.
    """
    budget = max_chars or settings.WORKSPACE_MAX_DIFF_CHARS
    per_file_limit = settings.WORKSPACE_MAX_FILE_DIFF_CHARS
    report = BuiltPrompt()

    changes = [FileChange(**entry) for entry in submission.diff_numstat or []]
    check_paths = [
        path
        for check in (exercise.grading_spec or {}).get("checks", [])
        for path in check.get("paths", [])
    ]

    elapsed_minutes = session.elapsed_seconds // 60
    limit_minutes = session.time_limit_seconds // 60

    # -- P0: never truncated ------------------------------------------------
    parts: list[str] = [
        "# EXERCISE",
        f"- Title: {exercise.title}",
        f"- Type: {exercise.get_exercise_type_display()}",
        f"- Difficulty: {exercise.difficulty}",
        f"- Time box: {limit_minutes} minutes"
        f" (author's estimate: {exercise.expected_time_minutes} minutes)",
        f"- Elapsed: {elapsed_minutes} minutes",
        f"- Ran out of time: {session.end_reason == session.EndReason.TIMED_OUT}",
        f"- Hints revealed: {session.hints_used} of {len(exercise.hints or [])}",
        "",
        "# THE BRIEF THE ENGINEER WAS GIVEN",
        exercise.brief_md,
        "",
        "# DEFINITION OF DONE",
        *(f"- {item}" for item in exercise.definition_of_done or []),
        "",
        "# PRIVATE GRADING NOTES (never shown to the engineer)",
        exercise.grading_notes or "(none authored)",
        "",
        "# AUTOMATED CHECK RESULTS (authoritative for whether the problem is solved)",
        _checks_table(check_summary),
        "",
        f"Objective signal status: {check_summary.objective_status}.",
        f"Required checks passed: {check_summary.required_passed_count}"
        f"/{len(check_summary.required_outcomes)}"
        f" (weighted {check_summary.required_weight_passed}/{check_summary.required_weight_total}).",
        f"Regressions: {len(check_summary.regressions)}"
        + (f" -> {check_summary.regressions[:10]}" if check_summary.regressions else ""),
        f"Stretch checks passed: {check_summary.stretch_passed_count}.",
        f"Protected files modified: {check_summary.tampered_paths or 'none'}.",
        "",
        "# EVERY CHANGED FILE (complete; the diff below may be trimmed)",
        _numstat_table(changes),
        f"\nTotals: {submission.files_changed} files, +{submission.lines_added} "
        f"-{submission.lines_deleted}, {submission.user_commit_count} commit(s).",
        "",
    ]

    if not submission.capture_ok:
        parts += [
            "# WARNING: THE WORKSPACE COULD NOT BE FULLY READ",
            f"{submission.capture_error}",
            "Grade what evidence exists and say plainly that the record is incomplete.",
            "",
        ]

    # -- P1: prose, never truncated ----------------------------------------
    notes = (session.user_notes or "").strip()
    markdown_files = {
        path: content
        for path, content in (submission.full_files or {}).items()
        if path.endswith((".md", ".rst", ".txt"))
    }

    # The in-app notes panel and a committed NOTES.md are two routes to the same
    # writeup, and an engineer may use either or both. Printing the same prose twice
    # presents one writeup as if it were two: length is one of the few proxies for
    # effort a reader has, so a duplicated writeup scores as more work than it was.
    # Collapse it, and say where it came from -- which source they used is information,
    # a second copy of the text is not.
    duplicated = [
        path for path, content in markdown_files.items() if _is_same_writeup(content, notes)
    ]
    for path in duplicated:
        # Same prose either way; take the longer copy in case one side carries a
        # trailing edit the other does not.
        if len(markdown_files[path].strip()) > len(notes):
            notes = markdown_files[path].strip()
        del markdown_files[path]

    parts += ["# NOTES.md AS SUBMITTED"]
    if duplicated:
        parts.append(
            f"(submitted identically via the notes panel and {', '.join(sorted(duplicated))}; "
            "shown once)"
        )
    parts.append(notes or "(the engineer left this empty)")
    for path, content in markdown_files.items():
        parts += ["", f"## {path}", content]
    parts.append("")

    # -- P2: commit log ----------------------------------------------------
    log_text, elided = _elide(submission.git_log or "", 6_000, label="the commit log")
    if elided:
        report.sections_truncated.append("git_log")
    parts += ["# COMMITS SINCE THE STARTING POINT (full bodies)", log_text or "(no commits)", ""]

    # -- P3: the diff ------------------------------------------------------
    spent = len("\n".join(parts))
    diff_budget = max(10_000, budget - spent - 20_000)
    parts += [
        "# THE CHANGE (unified diff against the starting commit)",
        _diff_section(
            submission.diff_text or "",
            changes,
            focus_paths=exercise.focus_paths or [],
            check_paths=check_paths,
            budget=diff_budget,
            per_file_limit=per_file_limit,
            report=report,
        ),
        "",
    ]

    # -- P4: surrounding code the reviewer needs ---------------------------
    excerpts = exercise.context_excerpts or []
    if excerpts:
        parts.append("# UNCHANGED CODE WORTH KNOWING ABOUT (for judging fit with the codebase)")
        for excerpt in excerpts:
            parts.append(
                f"- {excerpt.get('path')} lines {excerpt.get('line_range', '?')}: "
                f"{excerpt.get('why', '')}"
            )
        parts.append("")

    # -- P5: raw output, first to go ---------------------------------------
    failing_output = "\n\n".join(
        f"$ {outcome.check_id} ({outcome.kind})\n{outcome.output}"
        for outcome in check_summary.outcomes
        if not outcome.passed and outcome.output
    )
    if failing_output:
        remaining = budget - len("\n".join(parts))
        if remaining > 2_000:
            trimmed, elided = _elide(
                failing_output, min(remaining - 500, 8_000), label="command output"
            )
            if elided:
                report.sections_truncated.append("check_output")
            parts += ["# OUTPUT FROM THE CHECKS THAT DID NOT PASS", trimmed, ""]
        else:
            report.sections_truncated.append("check_output:dropped")

    report.text = "\n".join(parts)
    if report.truncated:
        logger.info(
            "grading prompt for session %s trimmed: %s",
            session.pk,
            report.sections_truncated,
        )
    return report
