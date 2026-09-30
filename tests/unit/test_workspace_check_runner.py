"""Tests for the objective check harness.

Two areas carry the most weight: JUnit parsing (the only source of per-test
granularity) and tamper detection (the one hard-F grading gate, so a false
positive is expensive and a false negative makes the whole system gameable).
"""

import textwrap

import pytest

from apps.workspace.enums import CheckKind, CheckStatus, ObjectiveStatus
from apps.workspace.schemas import Baseline, Check
from apps.workspace.services import check_runner
from apps.workspace.services.check_runner import CheckOutcome, CheckRunner, CheckRunSummary

# ---------------------------------------------------------------------------
# JUnit parsing
# ---------------------------------------------------------------------------

JUNIT_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="5">
  <testcase classname="tests.test_orders" name="test_total" file="tests/test_orders.py" time="0.01"/>
  <testcase classname="tests.test_orders" name="test_empty" file="tests/test_orders.py" time="0.01">
    <failure message="assert 0 == 1">boom</failure>
  </testcase>
  <testcase classname="tests.test_orders" name="test_broken" file="tests/test_orders.py">
    <error message="fixture error">kaput</error>
  </testcase>
  <testcase classname="tests.test_orders" name="test_later" file="tests/test_orders.py">
    <skipped message="not yet"/>
  </testcase>
  <testcase classname="tests.security.test_iso.TestCrossTenant" name="test_cte[0]"
            file="tests/security/test_iso.py"/>
</testsuite></testsuites>
"""


def test_parse_junit_maps_every_status():
    results = check_runner.parse_junit(JUNIT_SAMPLE)
    assert results["tests/test_orders.py::test_total"] == CheckStatus.PASSED
    assert results["tests/test_orders.py::test_empty"] == CheckStatus.FAILED
    assert results["tests/test_orders.py::test_broken"] == CheckStatus.ERROR
    assert results["tests/test_orders.py::test_later"] == CheckStatus.SKIPPED


def test_parse_junit_preserves_class_and_parameter_in_node_ids():
    """Parametrized tests inside classes must round-trip to a usable node id."""
    results = check_runner.parse_junit(JUNIT_SAMPLE)
    assert "tests/security/test_iso.py::TestCrossTenant::test_cte[0]" in results


def test_parse_junit_returns_empty_on_malformed_xml():
    """A broken report must degrade to indeterminate, not raise."""
    assert check_runner.parse_junit("<not xml") == {}


def test_junit_node_id_falls_back_to_classname_without_a_file_attribute():
    from xml.etree import ElementTree

    element = ElementTree.fromstring('<testcase classname="tests.test_orders" name="test_total"/>')
    assert check_runner.junit_node_id(element) == "tests/test_orders.py::test_total"


# ---------------------------------------------------------------------------
# Hashing and tamper detection
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    """A workspace with a protected security test and a config file."""
    ws = tmp_path / "ws"
    (ws / "tests" / "security").mkdir(parents=True)
    (ws / "nl2sql").mkdir()
    (ws / "tests" / "security" / "test_cross_tenant.py").write_text(
        "def test_cte_query_is_tenant_scoped():\n    assert False\n"
    )
    (ws / "nl2sql" / "policy.py").write_text("SQL = 'select 1'\n")
    return ws


def protected_check(workspace, **overrides) -> Check:
    hashes = check_runner.hash_paths(workspace, ["tests/security/**"])
    data = {
        "id": "R4",
        "kind": CheckKind.FILE_UNCHANGED,
        "paths": ["tests/security/**"],
        "expect": {"hashes": hashes},
        "required": True,
    }
    data.update(overrides)
    return Check(**data)


@pytest.mark.parametrize(
    "pattern",
    ["tests/security/**", "tests/security/", "tests/security/**/*", "tests/**/*.py"],
)
def test_protected_globs_actually_match_files(workspace, pattern):
    """Regression test for a silent false negative in the tampering gate.

    `Path.glob("tests/security/**")` yields only directories, so hashing returned
    an empty mapping and the protected-file check reported "all unchanged" no
    matter what had been edited. Every spelling an author might reasonably write
    must resolve to real files.
    """
    hashes = check_runner.hash_paths(workspace, [pattern])
    assert "tests/security/test_cross_tenant.py" in hashes, (
        f"pattern {pattern!r} matched no files, which would disable tamper detection"
    )


def test_hash_paths_is_stable_and_sorted(workspace):
    first = check_runner.hash_paths(workspace, ["tests/security/**"])
    second = check_runner.hash_paths(workspace, ["tests/security/**"])
    assert first == second
    assert list(first) == sorted(first)
    assert "tests/security/test_cross_tenant.py" in first


def test_untouched_protected_files_pass(workspace):
    runner = CheckRunner(workspace, use_container=False)
    outcome, offenders = runner._check_file_unchanged(protected_check(workspace))
    assert outcome.passed
    assert offenders == []


def test_editing_a_protected_test_is_detected(workspace):
    """The cheapest exploit: change the assertion instead of the code."""
    check = protected_check(workspace)
    (workspace / "tests" / "security" / "test_cross_tenant.py").write_text(
        "def test_cte_query_is_tenant_scoped():\n    assert True\n"
    )

    runner = CheckRunner(workspace, use_container=False)
    outcome, offenders = runner._check_file_unchanged(check)

    assert not outcome.passed
    assert offenders == ["tests/security/test_cross_tenant.py"]
    assert "modified" in outcome.actual


def test_deleting_a_protected_test_is_detected(workspace):
    check = protected_check(workspace)
    (workspace / "tests" / "security" / "test_cross_tenant.py").unlink()

    runner = CheckRunner(workspace, use_container=False)
    outcome, offenders = runner._check_file_unchanged(check)

    assert not outcome.passed
    assert "deleted" in outcome.actual


@pytest.mark.parametrize(
    "injected",
    [
        "@pytest.mark.skip(reason='later')\ndef test_cte_query_is_tenant_scoped():\n    assert False\n",
        "@pytest.mark.xfail\ndef test_cte_query_is_tenant_scoped():\n    assert False\n",
    ],
)
def test_skip_and_xfail_markers_are_detected(workspace, injected):
    """These neuter a test without necessarily changing its assertions."""
    check = protected_check(workspace)
    (workspace / "tests" / "security" / "test_cross_tenant.py").write_text(injected)

    runner = CheckRunner(workspace, use_container=False)
    outcome, offenders = runner._check_file_unchanged(check)

    assert not outcome.passed
    assert offenders


def test_adding_a_new_test_file_is_allowed(workspace):
    """Writing a new regression test is a stretch goal, not tampering."""
    check = protected_check(workspace)
    (workspace / "tests" / "security" / "test_my_new_case.py").write_text(
        "def test_extra():\n    assert True\n"
    )

    runner = CheckRunner(workspace, use_container=False)
    outcome, offenders = runner._check_file_unchanged(check)

    assert outcome.passed
    assert offenders == []
    assert "new files (allowed)" in outcome.actual


# ---------------------------------------------------------------------------
# grep checks
# ---------------------------------------------------------------------------


def test_grep_absent_passes_when_the_pattern_is_missing(workspace):
    check = Check(
        id="R5",
        kind=CheckKind.GREP_ABSENT,
        target=r"f\"[^\"]*\{tenant_id\}",
        paths=["nl2sql/**/*.py"],
    )
    runner = CheckRunner(workspace, use_container=False)
    assert runner._check_grep(check).passed


def test_grep_absent_fails_on_string_interpolated_sql(workspace):
    """The real check: interpolating a tenant id into SQL instead of binding it."""
    (workspace / "nl2sql" / "policy.py").write_text(
        'def scope(sql, tenant_id):\n    return f"{sql} AND tenant_id = {tenant_id}"\n'
    )
    check = Check(
        id="R5",
        kind=CheckKind.GREP_ABSENT,
        target=r"tenant_id = \{tenant_id\}",
        paths=["nl2sql/**/*.py"],
    )
    runner = CheckRunner(workspace, use_container=False)
    outcome = runner._check_grep(check)
    assert not outcome.passed
    assert "match(es)" in outcome.actual


def test_grep_errors_when_no_files_match_the_globs(workspace):
    """Silently passing because nothing was searched would be a false negative."""
    check = Check(id="R5", kind=CheckKind.GREP_ABSENT, target="anything", paths=["nowhere/**/*.py"])
    runner = CheckRunner(workspace, use_container=False)
    outcome = runner._check_grep(check)
    assert outcome.status == CheckStatus.ERROR
    assert not outcome.ran


# ---------------------------------------------------------------------------
# Regression detection
# ---------------------------------------------------------------------------


def test_suite_check_reports_no_regressions_when_baseline_holds(workspace):
    baseline = Baseline(passing_nodes=["tests/test_a.py::test_x", "tests/test_b.py::test_y"])
    runner = CheckRunner(workspace, baseline=baseline, use_container=False)
    results = {
        "tests/test_a.py::test_x": str(CheckStatus.PASSED),
        "tests/test_b.py::test_y": str(CheckStatus.PASSED),
    }
    check = Check(id="R3", kind=CheckKind.PYTEST_SUITE)
    assert runner._check_pytest_suite(check, results, "").passed


def test_suite_check_detects_collateral_damage(workspace):
    baseline = Baseline(passing_nodes=["tests/test_a.py::test_x", "tests/test_b.py::test_y"])
    runner = CheckRunner(workspace, baseline=baseline, use_container=False)
    results = {
        "tests/test_a.py::test_x": str(CheckStatus.PASSED),
        "tests/test_b.py::test_y": str(CheckStatus.FAILED),
    }
    check = Check(id="R3", kind=CheckKind.PYTEST_SUITE)
    outcome = runner._check_pytest_suite(check, results, "")
    assert not outcome.passed
    assert "1 regressed" in outcome.actual


def test_suite_check_treats_a_vanished_test_as_a_regression(workspace):
    """Deleting a passing test must not read as "still passing"."""
    baseline = Baseline(passing_nodes=["tests/test_a.py::test_x"])
    runner = CheckRunner(workspace, baseline=baseline, use_container=False)
    check = Check(id="R3", kind=CheckKind.PYTEST_SUITE)
    outcome = runner._check_pytest_suite(check, {"tests/other.py::test_z": "passed"}, "")
    assert not outcome.passed


def test_empty_report_is_an_error_not_a_pass(workspace):
    runner = CheckRunner(workspace, baseline=Baseline(), use_container=False)
    check = Check(id="R3", kind=CheckKind.PYTEST_SUITE)
    outcome = runner._check_pytest_suite(check, {}, "")
    assert outcome.status == CheckStatus.ERROR


# ---------------------------------------------------------------------------
# Metric comparison
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "op", "threshold", "expected"),
    [
        (1, "<=", 5, True),
        (5, "<=", 5, True),
        (6, "<=", 5, False),
        (0.84, ">=", 0.80, True),
        (0.79, ">=", 0.80, False),
        (3, "<", 3, False),
        (4, ">", 3, True),
        (3, "==", 3, True),
    ],
)
def test_compare_metric(workspace, value, op, threshold, expected):
    runner = CheckRunner(workspace, use_container=False)
    assert runner._compare_metric(value, op, threshold) is expected


def test_compare_metric_rejects_an_unknown_operator(workspace):
    runner = CheckRunner(workspace, use_container=False)
    with pytest.raises(ValueError, match="unknown comparison operator"):
        runner._compare_metric(1, "~=", 2)


# ---------------------------------------------------------------------------
# Summary aggregation
# ---------------------------------------------------------------------------


def outcome(check_id, *, passed, weight=1, required=True, stretch=False, status=None):
    resolved = status or (CheckStatus.PASSED if passed else CheckStatus.FAILED)
    return CheckOutcome(
        check_id=check_id,
        kind="pytest",
        status=str(resolved),
        passed=passed,
        weight=weight,
        required=required,
        stretch=stretch,
    )


def test_objective_correctness_is_weighted_not_counted():
    """A weight-4 check must matter more than a weight-1 check."""
    summary = CheckRunSummary(
        outcomes=[
            outcome("R1", passed=True, weight=3),
            outcome("R2", passed=False, weight=1),
        ]
    )
    assert summary.required_weight_total == 4
    assert summary.required_weight_passed == 3
    assert summary.objective_correctness == 75


def test_stretch_checks_are_excluded_from_correctness():
    summary = CheckRunSummary(
        outcomes=[
            outcome("R1", passed=True, weight=2),
            outcome("S1", passed=False, weight=5, required=False, stretch=True),
        ]
    )
    assert summary.required_weight_total == 2
    assert summary.objective_correctness == 100
    assert summary.stretch_passed_count == 0


def test_stretch_passes_are_counted():
    summary = CheckRunSummary(outcomes=[outcome("S1", passed=True, required=False, stretch=True)])
    assert summary.stretch_passed_count == 1


def test_objective_status_is_complete_when_every_check_decided():
    summary = CheckRunSummary(outcomes=[outcome("R1", passed=True), outcome("R2", passed=False)])
    assert summary.objective_status == ObjectiveStatus.COMPLETE


def test_objective_status_is_partial_when_one_check_could_not_run():
    summary = CheckRunSummary(
        outcomes=[
            outcome("R1", passed=True),
            outcome("R2", passed=False, status=CheckStatus.TIMEOUT),
        ]
    )
    assert summary.objective_status == ObjectiveStatus.PARTIAL


def test_objective_status_is_indeterminate_when_nothing_ran():
    """A broken environment must not be scored as a failed submission."""
    summary = CheckRunSummary(outcomes=[outcome("R1", passed=False, status=CheckStatus.ERROR)])
    assert summary.objective_status == ObjectiveStatus.INDETERMINATE


def test_objective_status_is_indeterminate_with_no_checks_at_all():
    assert CheckRunSummary().objective_status == ObjectiveStatus.INDETERMINATE


def test_tampering_detected_is_driven_by_offending_paths():
    summary = CheckRunSummary(tampered_paths=["tests/security/test_x.py"])
    assert summary.tampering_detected
    assert not CheckRunSummary().tampering_detected


def test_truncate_marks_the_elision():
    text = "x" * 100
    result = check_runner._truncate(text, limit=10)
    assert result.startswith("x" * 10)
    assert "90 characters omitted" in result


def test_truncate_leaves_short_text_alone():
    assert check_runner._truncate("short", limit=100) == "short"


# ---------------------------------------------------------------------------
# End-to-end against a real pytest run
# ---------------------------------------------------------------------------


def test_run_pytest_produces_real_results(tmp_path):
    """Exercise the actual pytest + junitxml + parse path, no container."""
    ws = tmp_path / "ws"
    (ws / "tests").mkdir(parents=True)
    (ws / "tests" / "test_demo.py").write_text(
        textwrap.dedent(
            """
            def test_passes():
                assert True

            def test_fails():
                assert 1 == 2
            """
        )
    )

    runner = CheckRunner(ws, use_container=False)
    results, output, exit_code, duration = runner.run_pytest()

    assert results, f"no results parsed; pytest said:\n{output}"
    statuses = {node.split("::")[-1]: status for node, status in results.items()}
    assert statuses["test_passes"] == CheckStatus.PASSED
    assert statuses["test_fails"] == CheckStatus.FAILED
    assert exit_code != 0
    assert duration >= 0
    # The scratch report must not be left behind in the graded tree.
    assert not list((ws / check_runner.GRADING_DIR).glob("junit-*.xml"))


def test_run_all_skips_llm_checks_for_the_evaluator(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    runner = CheckRunner(ws, use_container=False)
    summary = runner.run_all(
        [Check(id="R7", kind=CheckKind.LLM, description="audit logging is present")]
    )
    assert summary.outcomes[0].status == CheckStatus.SKIPPED
    assert not summary.outcomes[0].ran


def test_run_all_isolates_a_harness_error_to_one_check(tmp_path):
    """One malformed check must not void the whole run."""
    ws = tmp_path / "ws"
    ws.mkdir()
    runner = CheckRunner(ws, use_container=False)
    summary = runner.run_all(
        [
            Check(id="bad", kind=CheckKind.GREP_ABSENT, target="([unclosed", paths=["**/*.py"]),
            Check(id="ok", kind=CheckKind.FILE_UNCHANGED, paths=["**/*.py"], expect={"hashes": {}}),
        ]
    )
    assert summary.outcomes[0].status == CheckStatus.ERROR
    assert "harness error" in summary.outcomes[0].actual
    assert summary.outcomes[1].passed
