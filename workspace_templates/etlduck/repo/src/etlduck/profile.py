"""Profiling raw files before they are ingested.

The point of looking at a landing-zone file *before* loading it is to find out whether this
delivery looks like the last one. A schema change upstream, a truncated export or a shift in
a field's null spelling are all cheap to see here and expensive to discover three layers
later, after they have been averaged into a rollup.

Everything in this module reads text and counts. It does not parse timestamps or money --
that is silver's job, with quarantine reasons attached -- so a profile never rejects
anything and never fails. It describes.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

#: Spellings of "missing" seen in these exports. Compared after stripping and lowercasing.
NULL_TOKENS: frozenset[str] = frozenset({"", "null", "none", "n/a", "na", "-", "nil", "unknown"})

#: A field present in fewer than this share of records is reported as sparse. Not an error:
#: optional fields exist. It is here so a field that *used* to be universal and is now
#: nine-tenths absent shows up as a line in the report.
SPARSE_FIELD_THRESHOLD = 0.9


def is_null_token(value: object) -> bool:
    """Return whether a raw value should be read as missing.

    Args:
        value: The raw value, of any type as it came out of JSON.

    Returns:
        Whether it is absent or one of the recognised null spellings.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in NULL_TOKENS
    return False


@dataclass
class FieldProfile:
    """What was seen in one field across a file."""

    name: str
    present: int = 0
    null_like: int = 0
    distinct: int = 0
    examples: list[str] = field(default_factory=list)

    def presence(self, records: int) -> float:
        """Share of records in which this field appeared at all."""
        if records == 0:
            return 0.0
        return self.present / records

    def null_fraction(self) -> float:
        """Share of the field's appearances that were null-like."""
        if self.present == 0:
            return 0.0
        return self.null_like / self.present


@dataclass
class FileProfile:
    """What was seen in one raw file."""

    path: str
    lines: int = 0
    records: int = 0
    unparseable_lines: int = 0
    blank_lines: int = 0
    fields: dict[str, FieldProfile] = field(default_factory=dict)

    @property
    def parse_failure_fraction(self) -> float:
        """Share of non-blank lines that were not valid JSON."""
        candidates = self.records + self.unparseable_lines
        if candidates == 0:
            return 0.0
        return self.unparseable_lines / candidates

    def sparse_fields(self, threshold: float = SPARSE_FIELD_THRESHOLD) -> list[str]:
        """Fields appearing in fewer than ``threshold`` of records, sorted.

        Sorted so the report is stable between runs: this is read by a human comparing
        today's output against yesterday's, and an unstable order makes that diff useless.
        """
        return sorted(
            name
            for name, profile in self.fields.items()
            if profile.presence(self.records) < threshold
        )

    def findings(self) -> list[str]:
        """Return human-readable observations worth acting on, most structural first."""
        found: list[str] = []
        if self.records == 0:
            found.append(f"{self.path}: no parseable records at all")
            return found
        if self.unparseable_lines:
            found.append(
                f"{self.path}: {self.unparseable_lines} of "
                f"{self.records + self.unparseable_lines} lines are not valid JSON "
                f"({self.parse_failure_fraction:.1%})"
            )
        for name in self.sparse_fields():
            profile = self.fields[name]
            found.append(
                f"{self.path}: field {name!r} appears in only "
                f"{profile.presence(self.records):.0%} of records"
            )
        for name, profile in sorted(self.fields.items()):
            if profile.null_fraction() > 0.5:
                found.append(
                    f"{self.path}: field {name!r} is null-like in "
                    f"{profile.null_fraction():.0%} of the records that have it"
                )
            if profile.present and profile.distinct == 1:
                found.append(f"{self.path}: field {name!r} has a single distinct value")
        return found


def profile_jsonl(path: str | Path, example_limit: int = 3) -> FileProfile:
    """Profile a newline-delimited JSON file.

    Args:
        path: The file to read.
        example_limit: How many example values to keep per field.

    Returns:
        A :class:`FileProfile`.

    Raises:
        FileNotFoundError: If the file does not exist. Profiling a file that is not there
            is a different problem from profiling a bad one, and conflating them hides a
            broken upstream drop.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"no such file: {source}")

    result = FileProfile(path=source.name)
    seen: dict[str, Counter] = {}

    with source.open(encoding="utf-8") as handle:
        for line in handle:
            result.lines += 1
            stripped = line.strip()
            if not stripped:
                result.blank_lines += 1
                continue
            try:
                record = json.loads(stripped)
            except ValueError:
                result.unparseable_lines += 1
                continue
            if not isinstance(record, dict):
                result.unparseable_lines += 1
                continue

            result.records += 1
            for key, value in record.items():
                profile = result.fields.setdefault(key, FieldProfile(name=key))
                counter = seen.setdefault(key, Counter())
                profile.present += 1
                if is_null_token(value):
                    profile.null_like += 1
                else:
                    counter[str(value)] += 1

    for key, counter in seen.items():
        result.fields[key].distinct = len(counter)
        result.fields[key].examples = [value for value, _ in counter.most_common(example_limit)]
    return result


def profile_landing_zone(directory: str | Path, pattern: str = "*.jsonl") -> list[FileProfile]:
    """Profile every matching file in a directory.

    Args:
        directory: The landing zone.
        pattern: Glob for the files to profile.

    Returns:
        One :class:`FileProfile` per file, in sorted filename order.
    """
    return [profile_jsonl(path) for path in sorted(Path(directory).glob(pattern))]


def render_profiles(profiles: list[FileProfile]) -> str:
    """Render profiles as plain text for the CLI."""
    if not profiles:
        return "no files matched"
    lines: list[str] = []
    for profile in profiles:
        lines.append(f"{profile.path}")
        lines.append(
            f"  lines {profile.lines}  records {profile.records}  "
            f"unparseable {profile.unparseable_lines}  blank {profile.blank_lines}"
        )
        for name, field_profile in sorted(profile.fields.items()):
            lines.append(
                f"    {name:18} present {field_profile.presence(profile.records):6.1%}  "
                f"null-like {field_profile.null_fraction():6.1%}  "
                f"distinct {field_profile.distinct}"
            )
        findings = profile.findings()
        if findings:
            lines.append("  findings:")
            lines.extend(f"    - {finding}" for finding in findings)
        lines.append("")
    return "\n".join(lines)
