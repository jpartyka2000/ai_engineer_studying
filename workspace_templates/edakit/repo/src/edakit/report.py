"""Render a dataset profile as text or Markdown."""

from __future__ import annotations

from edakit.profile import DatasetProfile


def render_text(profile: DatasetProfile) -> str:
    """Render a profile as plain text for a terminal.

    Args:
        profile: The profile to render.

    Returns:
        The report.
    """
    lines = [
        "DATASET PROFILE",
        f"  rows    : {profile.row_count}",
        f"  columns : {profile.column_count}",
    ]
    if profile.missing is not None:
        lines.append(f"  complete rows: {profile.missing.complete_rows} "
                     f"({profile.missing.completeness:.0%})")

    lines += ["", "COLUMNS"]
    for name, column in profile.columns.items():
        lines.append(
            f"  {name:24} {column.inferred_type:12} "
            f"nulls={column.null_fraction:>5.0%} distinct={column.distinct_count}"
        )

    if profile.summaries:
        lines += ["", "NUMERIC SUMMARIES"]
        for name, summary in profile.summaries.items():
            lines.append(
                f"  {name:24} mean={summary.mean:<12.4g} median={summary.median:<12.4g} "
                f"sd={summary.stdev:<12.4g} min={summary.minimum:<10.4g} max={summary.maximum:.4g}"
            )

    warnings = profile.warnings()
    lines += ["", f"FINDINGS ({len(warnings)})"]
    lines += [f"  - {warning}" for warning in warnings] or ["  none"]
    return "\n".join(lines) + "\n"


def render_markdown(profile: DatasetProfile) -> str:
    """Render a profile as Markdown, for pasting into a ticket or a notebook.

    Args:
        profile: The profile to render.

    Returns:
        The report.
    """
    lines = [
        "# Dataset profile",
        "",
        f"- **Rows:** {profile.row_count}",
        f"- **Columns:** {profile.column_count}",
    ]
    if profile.missing is not None:
        lines.append(f"- **Complete rows:** {profile.missing.complete_rows} "
                     f"({profile.missing.completeness:.0%})")

    lines += ["", "## Columns", "", "| column | type | nulls | distinct |", "|---|---|---|---|"]
    for name, column in profile.columns.items():
        lines.append(
            f"| `{name}` | {column.inferred_type} | {column.null_fraction:.0%} "
            f"| {column.distinct_count} |"
        )

    if profile.summaries:
        lines += [
            "",
            "## Numeric summaries",
            "",
            "| column | mean | median | sd | min | max |",
            "|---|---|---|---|---|---|",
        ]
        for name, summary in profile.summaries.items():
            lines.append(
                f"| `{name}` | {summary.mean:.4g} | {summary.median:.4g} | {summary.stdev:.4g} "
                f"| {summary.minimum:.4g} | {summary.maximum:.4g} |"
            )

    warnings = profile.warnings()
    lines += ["", "## Findings", ""]
    lines += [f"- {warning}" for warning in warnings] or ["_Nothing worth flagging._"]
    return "\n".join(lines) + "\n"
