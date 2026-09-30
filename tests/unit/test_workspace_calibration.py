"""Tests for the calibration harness's pure logic.

The expensive half of calibration -- scaffolding, containers, the model call -- is
covered by actually running it. What is covered here is everything that could silently
corrupt a round's *conclusion*: an edit that quietly matches the wrong number of
places, a scoresheet typo swallowed into a fake disagreement, and the two statistics
the report draws its verdict from.
"""

import json

import pytest

from apps.workspace.calibration import personas, report, store
from apps.workspace.calibration.spec import (
    Commit,
    Edit,
    Persona,
    PersonaError,
    PersonaRegistry,
)
from apps.workspace.calibration.store import AnswerKeyEntry, HumanGrade


def make_persona(**overrides) -> Persona:
    """Build a persona with sensible defaults for tests."""
    defaults = {
        "persona_id": "p1",
        "exercise_slug": "ex-001-example",
        "tier": "a tier",
        "rationale": "why",
        "predicted_letter": "B",
        "notes_md": "notes",
        "commits": (Commit(message="msg", edits=(Edit(path="a.txt", content="x"),)),),
    }
    return Persona(**{**defaults, **overrides})


def entry(item: str, *, system: str, dimensions=None, **overrides) -> AnswerKeyEntry:
    """Build an answer-key entry with a system letter already recorded."""
    defaults = {
        "item": item,
        "persona_key": f"ex-001-example/{item}",
        "exercise_slug": "ex-001-example",
        "persona_id": item,
        "tier": "tier",
        "rationale": "rationale",
        "predicted_letter": "B",
        "session_id": 1,
        "system_letter": system,
        "system_dimensions": dimensions or {},
    }
    return AnswerKeyEntry(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Edits
# ---------------------------------------------------------------------------


def test_edit_requires_exactly_one_of_find_or_content():
    with pytest.raises(ValueError, match="exactly one"):
        Edit(path="a.txt")
    with pytest.raises(ValueError, match="exactly one"):
        Edit(path="a.txt", find="x", content="y")


def test_edit_replaces_an_anchored_string(tmp_path):
    (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")
    Edit(path="a.txt", find="world", replace="there").apply_to(tmp_path)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello there"


def test_edit_raises_when_the_anchor_count_is_wrong(tmp_path):
    """A persona that meant to change both call sites must not silently change one."""
    (tmp_path / "a.txt").write_text("x\nx\n", encoding="utf-8")
    with pytest.raises(PersonaError, match="expected 1 occurrence"):
        Edit(path="a.txt", find="x", replace="y").apply_to(tmp_path)

    Edit(path="a.txt", find="x", replace="y", count=2).apply_to(tmp_path)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "y\ny\n"


def test_edit_raises_for_a_missing_file(tmp_path):
    with pytest.raises(PersonaError, match="does not exist"):
        Edit(path="nope.txt", find="x", replace="y").apply_to(tmp_path)


def test_edit_writing_whole_content_creates_parent_directories(tmp_path):
    Edit(path="deep/dir/a.txt", content="body").apply_to(tmp_path)
    assert (tmp_path / "deep/dir/a.txt").read_text(encoding="utf-8") == "body"


# ---------------------------------------------------------------------------
# The registry and the authored corpus
# ---------------------------------------------------------------------------


def test_registry_rejects_duplicate_keys():
    registry = PersonaRegistry()
    registry.add(make_persona())
    with pytest.raises(ValueError, match="duplicate persona"):
        registry.add(make_persona())


def test_every_authored_persona_has_a_unique_item_id():
    store.assert_unique_item_ids([persona.key for persona in personas.all_personas()])


def test_item_ids_are_stable_across_runs():
    """Ids are hashes, so a rebuild must not renumber packets the user is mid-way
    through grading."""
    assert store.item_id("ex-005-x/root-cause") == store.item_id("ex-005-x/root-cause")
    assert store.item_id("ex-005-x/root-cause") != store.item_id("ex-005-x/silent")


def test_authored_personas_predict_a_valid_letter():
    from apps.workspace.grading import LETTERS_BEST_FIRST

    for persona in personas.all_personas():
        assert persona.predicted_letter in LETTERS_BEST_FIRST, persona.key


def test_each_exercise_has_personas_spanning_more_than_one_predicted_tier():
    """A round whose items are all the same quality cannot test discrimination."""
    for slug in personas.REGISTRY.exercise_slugs:
        predicted = {p.predicted_letter for p in personas.personas_for(slug)}
        assert len(predicted) > 1, f"{slug} personas all predict the same letter"


# ---------------------------------------------------------------------------
# The scoresheet
# ---------------------------------------------------------------------------


def test_render_then_parse_round_trips_a_filled_sheet():
    filled = HumanGrade(
        item="item-0001",
        letter="B+",
        dimensions={"correctness": 90, "documentation": 40},
        comment="terse",
    )
    text = store.render_scoresheet(["item-0001"], existing={"item-0001": filled})
    parsed = store.parse_scoresheet(text)
    assert parsed["item-0001"] == filled


def test_a_blank_letter_leaves_the_item_unfilled():
    parsed = store.parse_scoresheet(store.render_scoresheet(["item-0001"]))
    assert parsed["item-0001"].filled is False


def test_parse_accepts_lowercase_letters_and_free_annotation():
    text = "## item-0001\nletter: b+\nsome prose the user added\ncomment: fine\n"
    parsed = store.parse_scoresheet(text)
    assert parsed["item-0001"].letter == "B+"
    assert parsed["item-0001"].comment == "fine"


def test_parse_rejects_a_letter_off_the_scale():
    with pytest.raises(ValueError, match="not a letter grade"):
        store.parse_scoresheet("## item-0001\nletter: E\n")


@pytest.mark.parametrize("value", ["abc", "101", "-1"])
def test_parse_rejects_an_out_of_range_dimension(value):
    with pytest.raises(ValueError):
        store.parse_scoresheet(f"## item-0001\nletter: B\ncorrectness: {value}\n")


def test_parse_ignores_content_before_any_item_heading():
    parsed = store.parse_scoresheet("letter: A\n\n## item-0001\nletter: C\n")
    assert list(parsed) == ["item-0001"]
    assert parsed["item-0001"].letter == "C"


# ---------------------------------------------------------------------------
# Comparison arithmetic
# ---------------------------------------------------------------------------


def comparison(human: str, system: str, **kwargs) -> report.Comparison:
    """Build one comparison from a pair of letters."""
    return report.Comparison(
        entry=entry("item-0001", system=system, dimensions=kwargs.get("system_dimensions")),
        human=HumanGrade(
            item="item-0001", letter=human, dimensions=kwargs.get("human_dimensions", {})
        ),
    )


@pytest.mark.parametrize(
    ("human", "system", "steps", "direction"),
    [
        ("B", "B", 0, "exact"),
        ("B", "B-", 1, "system harsher"),
        ("B", "B+", -1, "system lenient"),
        ("A", "F", 11, "system harsher"),
    ],
)
def test_steps_and_direction(human, system, steps, direction):
    result = comparison(human, system)
    assert result.steps == steps
    assert result.direction == direction


def test_agreement_tolerance_is_one_step():
    assert comparison("B", "B-").agrees is True
    assert comparison("B", "C+").agrees is False


def test_weighted_contribution_ranks_by_weight_not_raw_delta():
    """A 40-point documentation gap moves the score less than a 30-point correctness
    gap, and the report must point at the one that actually moved the letter."""
    result = comparison(
        "B",
        "C",
        human_dimensions={"correctness": 90, "documentation": 80},
        system_dimensions={"correctness": 60, "documentation": 40},
    )
    ranked = result.weighted_contribution()
    assert ranked[0][0] == "correctness"
    # correctness -30 at 50%, documentation -40 at 15%: the larger raw delta contributes
    # less, which is the whole point of ranking by weighted contribution.
    assert ranked[0][1] == pytest.approx(-15.0)
    assert ranked[1][1] == pytest.approx(-6.0)


# ---------------------------------------------------------------------------
# Round-level verdicts
# ---------------------------------------------------------------------------


def make_round(pairs: list[tuple[str, str, str]]) -> report.Round:
    """Build a round from ``(item, human_letter, system_letter)`` triples."""
    return report.Round(
        comparisons=[
            report.Comparison(
                entry=entry(item, system=system),
                human=HumanGrade(item=item, letter=human),
            )
            for item, human, system in pairs
        ]
    )


def test_gate_passes_only_when_every_item_is_within_one_step():
    assert make_round([("a", "B", "B-"), ("b", "A", "A")]).gate_passed is True
    assert make_round([("a", "B", "B-"), ("b", "A", "B")]).gate_passed is False


def test_an_empty_round_never_passes_the_gate():
    """Zero comparisons must not read as unanimous agreement."""
    assert report.Round().gate_passed is False


def test_mean_signed_steps_detects_a_systematic_bias():
    harsh = make_round([("a", "B", "B-"), ("b", "A", "A-"), ("c", "C", "C-")])
    assert harsh.mean_signed_steps == pytest.approx(1.0)
    assert harsh.mean_absolute_steps == pytest.approx(1.0)

    mixed = make_round([("a", "B", "B-"), ("b", "A", "A+")])
    assert mixed.mean_signed_steps == pytest.approx(0.0)
    assert mixed.mean_absolute_steps == pytest.approx(1.0)


def test_inversions_catch_a_backwards_ranking():
    """The system agreeing on letters but ordering two submissions backwards is the
    failure the report must never miss."""
    backwards = make_round([("strong", "A", "C"), ("weak", "C", "A")])
    assert len(backwards.inversions()) == 1

    ordered = make_round([("strong", "A", "B"), ("weak", "C", "D")])
    assert ordered.inversions() == []


def test_ties_are_not_inversions():
    assert make_round([("a", "B", "B"), ("b", "B", "C")]).inversions() == []


def test_a_system_tie_across_a_wide_human_gap_is_a_collapsed_pair():
    """The rubric giving the same letter to work the human placed four steps apart is a
    discrimination failure, even though the ordering is not backwards."""
    round_ = make_round([("strong", "A", "C"), ("weak", "C", "C")])
    assert round_.inversions() == []
    assert len(round_.collapsed_pairs()) == 1
    assert "COLLAPSED PAIRS" in report.render(round_)


def test_a_narrow_human_gap_is_not_a_collapsed_pair():
    """Splitting B+/B by hand and getting one letter back is agreement, not a failure."""
    assert make_round([("a", "B+", "B"), ("b", "B", "B")]).collapsed_pairs() == []


def test_a_collapsed_pair_fails_the_verdict_even_when_every_letter_agrees():
    round_ = make_round([("a", "B+", "B"), ("b", "B-", "B")])
    assert round_.gate_passed is True
    assert len(round_.collapsed_pairs()) == 1
    assert "Gate NOT passed" in report.render(round_)


def test_inversions_are_only_computed_within_an_exercise():
    round_ = report.Round(
        comparisons=[
            report.Comparison(
                entry=entry("a", system="C", exercise_slug="ex-001-example"),
                human=HumanGrade(item="a", letter="A"),
            ),
            report.Comparison(
                entry=entry("b", system="A", exercise_slug="ex-002-other"),
                human=HumanGrade(item="b", letter="C"),
            ),
        ]
    )
    assert round_.inversions() == []


# ---------------------------------------------------------------------------
# Reporting and persistence
# ---------------------------------------------------------------------------


def test_render_reports_nothing_to_compare_without_inventing_agreement():
    text = report.render(report.Round(ungraded=[entry("a", system="")]))
    assert "Nothing to compare" in text
    assert "PASSED" not in text


def test_a_cancelling_dimension_is_reported_as_noise_not_bias():
    """Scored 40 too high on one item and 40 too low on another, a dimension nets to
    zero. That is an ambiguous definition, not an anchor to shift, and the report must
    say so instead of hiding it in the average."""
    round_ = report.Round(
        comparisons=[
            report.Comparison(
                entry=entry("a", system="B", dimensions={"correctness": 90}),
                human=HumanGrade(item="a", letter="F", dimensions={"correctness": 50}),
            ),
            report.Comparison(
                entry=entry("b", system="F", dimensions={"correctness": 50}),
                human=HumanGrade(item="b", letter="B", dimensions={"correctness": 90}),
            ),
        ]
    )
    biased, noisy = report._dimension_offenders(round_)
    assert biased == ("correctness", pytest.approx(0.0))
    assert noisy is not None and noisy[0] == "correctness"
    assert "BOTH directions" in report.render(round_)


def test_a_consistent_offset_is_not_reported_as_noise():
    round_ = report.Round(
        comparisons=[
            report.Comparison(
                entry=entry(item, system="C", dimensions={"documentation": 20}),
                human=HumanGrade(item=item, letter="B", dimensions={"documentation": 60}),
            )
            for item in ("a", "b")
        ]
    )
    biased, noisy = report._dimension_offenders(round_)
    assert biased == ("documentation", pytest.approx(-12.0))
    assert noisy is None


def test_render_names_the_dominant_dimension_when_the_gate_fails():
    round_ = report.Round(
        comparisons=[
            report.Comparison(
                entry=entry("a", system="D", dimensions={"documentation": 10}),
                human=HumanGrade(item="a", letter="B", dimensions={"documentation": 70}),
            )
        ]
    )
    text = report.render(round_)
    assert "Gate NOT passed" in text
    assert "documentation" in text


def test_archive_appends_rather_than_overwriting(tmp_path, settings):
    settings.WORKSPACE_CALIBRATION_ROOT = tmp_path
    report.archive(make_round([("a", "B", "B")]))
    report.archive(make_round([("b", "A", "A")]))
    payload = json.loads(store.grades_archive_path().read_text(encoding="utf-8"))
    assert len(payload["rounds"]) == 2


def test_answer_key_round_trips(tmp_path, settings):
    settings.WORKSPACE_CALIBRATION_ROOT = tmp_path
    written = [entry("item-0001", system="B+", dimensions={"correctness": 90})]
    store.write_answer_key(written)
    assert store.read_answer_key() == written


def test_answer_key_carries_its_warning_banner(tmp_path, settings):
    settings.WORKSPACE_CALIBRATION_ROOT = tmp_path
    store.write_answer_key([entry("item-0001", system="B")])
    raw = store.answer_key_path().read_text(encoding="utf-8")
    assert "DO NOT READ THIS FILE" in raw
