"""On-disk layout for a calibration round: packets, answer key, scoresheet, archive.

Three files carry state and each has a different lifetime, which is why they are
separate rather than one blob:

* ``answer-key.json`` -- written at build time, read only by the reveal. It maps opaque
  item ids back to personas. **Reading it before grading defeats the exercise**, hence
  the name and the banner inside it.
* ``scoresheet.md`` -- the human's input, edited by hand. Markdown with a strict
  ``key: value`` body per item, because a format you can fill in from a terminal
  without fighting JSON quoting is a format that actually gets filled in.
* ``grades.json`` -- the archive. Every graded round is appended, never overwritten, so
  the corpus accumulates into the ``grade_replay`` regression set the plan calls for.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.workspace.grading import LETTERS_BEST_FIRST

ITEM_ID_LENGTH = 4

#: Written into the answer key so an accidental `cat` is at least self-limiting.
ANSWER_KEY_BANNER = (
    "DO NOT READ THIS FILE until you have filled in scoresheet.md. It maps every "
    "item id to the persona that produced it and the letter that was predicted for "
    "it, which is exactly the information the blind grading is trying to keep out of "
    "your head."
)

_FIELD_RE = re.compile(r"^(?P<key>[a-z_]+)\s*:\s*(?P<value>.*)$")
_HEADING_RE = re.compile(r"^##\s+(?P<item>item-[0-9a-f]+)\s*$")

DIMENSION_KEYS = ("correctness", "engineering", "documentation", "completeness")


def calibration_root() -> Path:
    """Return the directory holding calibration state."""
    return Path(settings.WORKSPACE_CALIBRATION_ROOT)


def packets_dir() -> Path:
    """Return the directory blind packets are written to."""
    return calibration_root() / "packets"


def answer_key_path() -> Path:
    """Return the path of the item-id-to-persona map."""
    return calibration_root() / "answer-key.json"


def scoresheet_path() -> Path:
    """Return the path of the hand-filled scoresheet."""
    return calibration_root() / "scoresheet.md"


def grades_archive_path() -> Path:
    """Return the path of the accumulated human-versus-system record."""
    return calibration_root() / "grades.json"


def item_id(persona_key: str) -> str:
    """Return the opaque packet id for a persona.

    Derived from the persona key by hash rather than assigned sequentially, so that
    rebuilding one exercise's personas does not renumber another's, and so the id
    carries no hint of tier or authoring order.

    Args:
        persona_key: The persona's ``exercise-slug/persona-id`` key.

    Returns:
        An id of the form ``item-a3f9``.
    """
    digest = hashlib.sha256(persona_key.encode("utf-8")).hexdigest()
    return f"item-{digest[:ITEM_ID_LENGTH]}"


def assert_unique_item_ids(persona_keys: list[str]) -> None:
    """Raise if two personas would share a packet id.

    Args:
        persona_keys: Every persona key in the round.

    Raises:
        ValueError: On a collision, naming both personas. With a 4-hex-digit id this
            becomes likely around 300 personas; the fix is to raise
            :data:`ITEM_ID_LENGTH`, and finding out by assertion beats finding out by
            one packet silently overwriting another.
    """
    seen: dict[str, str] = {}
    for key in persona_keys:
        ident = item_id(key)
        if ident in seen:
            raise ValueError(
                f"item id {ident} collides between {seen[ident]!r} and {key!r}; "
                "raise ITEM_ID_LENGTH"
            )
        seen[ident] = key


@dataclass
class AnswerKeyEntry:
    """What the reveal needs to know about one built item."""

    item: str
    persona_key: str
    exercise_slug: str
    persona_id: str
    tier: str
    rationale: str
    predicted_letter: str
    session_id: int
    system_letter: str = ""
    system_score: int = 0
    system_dimensions: dict[str, int] = field(default_factory=dict)
    applied_caps: list[str] = field(default_factory=list)
    symptom_patch_suspected: bool = False
    objective_status: str = ""
    required_passed: str = ""
    degraded: bool = False
    built_at: str = ""
    error: str = ""

    @property
    def graded(self) -> bool:
        """Whether the system produced a letter for this item."""
        return bool(self.system_letter)


def write_answer_key(entries: list[AnswerKeyEntry]) -> Path:
    """Write the answer key, replacing any previous round.

    Args:
        entries: One entry per built item.

    Returns:
        The path written.
    """
    path = answer_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_warning": ANSWER_KEY_BANNER,
        "items": [asdict(entry) for entry in entries],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_answer_key() -> list[AnswerKeyEntry]:
    """Read the answer key.

    Returns:
        Every entry from the current round, or an empty list if none was written.
    """
    path = answer_key_path()
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [AnswerKeyEntry(**entry) for entry in payload.get("items", [])]


@dataclass
class HumanGrade:
    """One hand-assigned grade parsed out of the scoresheet."""

    item: str
    letter: str = ""
    dimensions: dict[str, int] = field(default_factory=dict)
    comment: str = ""

    @property
    def filled(self) -> bool:
        """Whether a letter was actually recorded."""
        return bool(self.letter)


def render_scoresheet(items: list[str], *, existing: dict[str, HumanGrade] | None = None) -> str:
    """Render a blank scoresheet, preserving anything already filled in.

    Args:
        items: Item ids to include, in packet order.
        existing: Previously parsed grades to carry forward.

    Returns:
        The scoresheet markdown.
    """
    existing = existing or {}
    letters = " ".join(LETTERS_BEST_FIRST)
    lines = [
        "# Calibration scoresheet",
        "",
        "Read each packet in `packets/`, then fill in the block below it. Grade the",
        "submission as you would a colleague's pull request, using the same brief,",
        "checks and private grading notes the model was given -- every packet is the",
        "verbatim prompt the grader received.",
        "",
        f"`letter:` is required, one of: {letters}",
        "",
        "The four dimension scores are optional but worth doing on at least a few:",
        "a letter alone tells you *that* the rubric disagrees, the dimensions tell you",
        "*which* of them is miscalibrated, which is the part you would actually change.",
        "Weights are correctness 40, engineering 25, documentation 25, completeness 10.",
        "",
        "Do not open `answer-key.json` until you are done.",
        "",
    ]
    for item in items:
        prior = existing.get(item, HumanGrade(item=item))
        lines += [
            f"## {item}",
            "",
            f"letter: {prior.letter}",
        ]
        for key in DIMENSION_KEYS:
            value = prior.dimensions.get(key, "")
            lines.append(f"{key}: {value}")
        lines += [f"comment: {prior.comment}", ""]
    return "\n".join(lines)


def parse_scoresheet(text: str) -> dict[str, HumanGrade]:
    """Parse a filled-in scoresheet.

    Unknown keys and prose outside an item block are ignored, so the sheet can be
    annotated freely. A blank ``letter:`` leaves the item unfilled rather than
    defaulting to anything.

    Args:
        text: The scoresheet's contents.

    Returns:
        Grades keyed by item id, including unfilled ones.

    Raises:
        ValueError: If a letter is not on the 13-point scale, or a dimension score is
            not an integer in 0-100. Silently dropping a typo here would show up as a
            fake disagreement in the report.
    """
    grades: dict[str, HumanGrade] = {}
    current: HumanGrade | None = None
    for raw in text.splitlines():
        heading = _HEADING_RE.match(raw.strip())
        if heading:
            current = HumanGrade(item=heading.group("item"))
            grades[current.item] = current
            continue
        if current is None:
            continue
        match = _FIELD_RE.match(raw.strip())
        if not match:
            continue
        key, value = match.group("key"), match.group("value").strip()
        if not value:
            continue
        if key == "letter":
            if value.upper() not in LETTERS_BEST_FIRST:
                raise ValueError(f"{current.item}: {value!r} is not a letter grade")
            current.letter = value.upper()
        elif key in DIMENSION_KEYS:
            try:
                score = int(value)
            except ValueError:
                raise ValueError(
                    f"{current.item}: {key} must be an integer, got {value!r}"
                ) from None
            if not 0 <= score <= 100:
                raise ValueError(f"{current.item}: {key} must be 0-100, got {score}")
            current.dimensions[key] = score
        elif key == "comment":
            current.comment = value
    return grades


def append_to_archive(round_payload: dict[str, Any]) -> Path:
    """Append a completed round to the accumulated archive.

    Appending rather than overwriting is what turns repeated calibration rounds into
    the regression corpus: every hand-assigned letter ever recorded stays available to
    assert against when the evaluator prompt changes.

    Args:
        round_payload: The round's comparison record.

    Returns:
        The archive path.
    """
    path = grades_archive_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rounds: list[dict[str, Any]] = []
    if path.is_file():
        rounds = json.loads(path.read_text(encoding="utf-8")).get("rounds", [])
    rounds.append(round_payload)
    path.write_text(json.dumps({"rounds": rounds}, indent=2) + "\n", encoding="utf-8")
    return path
