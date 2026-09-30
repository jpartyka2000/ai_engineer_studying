"""Run objective acceptance checks against a scaffolded workspace.

This is where roughly half of every grade comes from. The design goals, in order:

1. **Never trust captured output.** The harness re-runs the tests itself. Scoring a
   user-pasted test report would make passing a one-line edit.
2. **Run inside the exercise's own container**, never in the study app's Python
   process. That keeps the study app's dependencies completely decoupled from the
   seven base apps', none of which it could otherwise satisfy.
3. **Per-test granularity with zero new dependencies.** ``--junitxml`` plus the
   standard library's ``xml.etree`` gives the same information as
   ``pytest-json-report`` without adding a package -- which matters because
   ``pip install`` in this environment has failed with SSL errors before.
4. **An environment failure is not a zero.** If Docker is down or a command times
   out, the objective portion is marked indeterminate and grading falls back to
   model judgment, labelled provisional. A broken laptop must never score an F.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree

from django.conf import settings

from apps.workspace.enums import CheckKind, CheckStatus, ObjectiveStatus
from apps.workspace.schemas import Baseline, Check

logger = logging.getLogger(__name__)

#: Raw command output kept per check, so a results page stays readable.
MAX_OUTPUT_CHARS: Final[int] = 8_000

#: Service name inside an exercise's docker-compose that runs the app and tests.
APP_SERVICE: Final[str] = "app"

#: Directory inside the workspace used for harness scratch files (junit XML etc).
#: Excluded from the graded diff.
GRADING_DIR: Final[str] = ".grading"

#: Environment variables that make CI-shaped flakiness reproducible: unsorted
#: hashing, UTC, and no pytest cache to carry ordering between runs.
CI_ENV: Final[dict[str, str]] = {
    "TZ": "UTC",
    "PYTHONHASHSEED": "random",
    "CI": "true",
}


@dataclass
class CheckOutcome:
    """The result of running one acceptance check."""

    check_id: str
    kind: str
    status: str
    passed: bool
    weight: int = 1
    required: bool = True
    stretch: bool = False
    expected: str = ""
    actual: str = ""
    duration_ms: int = 0
    output: str = ""
    description: str = ""

    @property
    def ran(self) -> bool:
        """Whether the check produced a real verdict.

        ``ERROR`` and ``TIMEOUT`` mean the harness could not decide, which is
        different from deciding "failed".
        """
        return self.status in {CheckStatus.PASSED, CheckStatus.FAILED}


@dataclass
class CheckRunSummary:
    """Aggregate objective signal for a submission."""

    outcomes: list[CheckOutcome] = field(default_factory=list)
    regressions: list[str] = field(default_factory=list)
    tampered_paths: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def required_outcomes(self) -> list[CheckOutcome]:
        """Checks that gate correctness."""
        return [outcome for outcome in self.outcomes if outcome.required]

    @property
    def required_weight_total(self) -> int:
        """Total weight of all required checks."""
        return sum(outcome.weight for outcome in self.required_outcomes)

    @property
    def required_weight_passed(self) -> int:
        """Weight of the required checks that passed."""
        return sum(o.weight for o in self.required_outcomes if o.passed)

    @property
    def required_passed_count(self) -> int:
        """Number of required checks that passed."""
        return sum(1 for outcome in self.required_outcomes if outcome.passed)

    @property
    def stretch_passed_count(self) -> int:
        """Number of stretch checks that passed."""
        return sum(1 for outcome in self.outcomes if outcome.stretch and outcome.passed)

    @property
    def tampering_detected(self) -> bool:
        """Whether any protected file was modified."""
        return bool(self.tampered_paths)

    @property
    def objective_correctness(self) -> int:
        """Weighted proportion of required checks passing, as 0-100.

        Returns 0 when an exercise declares no required checks; callers should
        consult ``objective_status`` before using this.
        """
        total = self.required_weight_total
        if total == 0:
            return 0
        return int(round(100 * self.required_weight_passed / total))

    @property
    def objective_status(self) -> str:
        """Whether the objective half of the grade could be determined.

        Checks of kind ``llm`` are excluded: they are deliberately delegated to the
        evaluator rather than executed here, so counting them as "did not run" would
        mean any exercise declaring one could never report ``COMPLETE`` -- which in
        turn would silently skip the ``min(objective, model)`` reconciliation and let
        a model score stand unchecked.
        """
        mechanical = [o for o in self.outcomes if o.kind != CheckKind.LLM]
        if not mechanical:
            return ObjectiveStatus.INDETERMINATE
        if all(not outcome.ran for outcome in mechanical):
            return ObjectiveStatus.INDETERMINATE
        if any(not outcome.ran for outcome in mechanical):
            return ObjectiveStatus.PARTIAL
        return ObjectiveStatus.COMPLETE


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Trim long output, marking the elision so it is never mistaken for the whole."""
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit] + f"\n... [{omitted} characters omitted] ..."


def junit_node_id(testcase: ElementTree.Element) -> str:
    """Build a pytest node id from a JUnit ``<testcase>`` element.

    pytest records ``file`` and ``line`` attributes, which give an exact node id.
    Without them the id is reconstructed from the dotted ``classname``, which is
    lossy for tests inside classes -- hence the preference order.

    Args:
        testcase: A ``<testcase>`` element.

    Returns:
        A node id such as ``tests/test_orders.py::test_total[3]``.
    """
    name = testcase.get("name", "")
    classname = testcase.get("classname", "")
    file_attr = testcase.get("file")

    if file_attr:
        # Preserve the class segment when the test lives inside a class.
        tail = classname.rsplit(".", 1)[-1] if classname else ""
        if tail and tail[:1].isupper():
            return f"{file_attr}::{tail}::{name}"
        return f"{file_attr}::{name}"

    if not classname:
        return name
    parts = classname.split(".")
    if parts[-1][:1].isupper() and len(parts) > 1:
        module = "/".join(parts[:-1])
        return f"{module}.py::{parts[-1]}::{name}"
    return f"{'/'.join(parts)}.py::{name}"


def parse_junit(xml_text: str) -> dict[str, str]:
    """Parse JUnit XML into a node-id to status map.

    Args:
        xml_text: The contents of a ``--junitxml`` report.

    Returns:
        Mapping of pytest node id to one of ``passed``/``failed``/``error``/
        ``skipped``. An unparseable report yields an empty mapping rather than
        raising, so a malformed report degrades to "indeterminate".
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        logger.warning("could not parse JUnit XML report")
        return {}

    results: dict[str, str] = {}
    for testcase in root.iter("testcase"):
        node_id = junit_node_id(testcase)
        if testcase.find("error") is not None:
            status = CheckStatus.ERROR
        elif testcase.find("failure") is not None:
            status = CheckStatus.FAILED
        elif testcase.find("skipped") is not None:
            status = CheckStatus.SKIPPED
        else:
            status = CheckStatus.PASSED
        results[node_id] = str(status)
    return results


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_matching_files(workspace: Path, pattern: str):
    """Yield every *file* under ``workspace`` matching a glob pattern.

    ``Path.glob`` treats a trailing ``**`` as "this directory and all
    subdirectories", so it yields directories and no files at all. Authors
    naturally write ``tests/security/**`` meaning "everything under here", so that
    spelling is expanded to also try ``tests/security/**/*``.

    Getting this wrong is not a cosmetic bug: an empty match set makes the
    protected-file check report "all unchanged" no matter what was edited, which
    would silently disable the test-tampering gate.

    Args:
        workspace: The root that patterns are relative to.
        pattern: A glob such as ``"tests/security/**"`` or ``"attack/x.jsonl"``.

    Yields:
        Matching file paths, in sorted order, without duplicates.
    """
    spellings = [pattern]
    if pattern.endswith("**"):
        spellings.append(pattern + "/*")
    elif pattern.endswith("/"):
        spellings.append(pattern + "**/*")

    seen: set[Path] = set()
    for spelling in spellings:
        try:
            matches = sorted(workspace.glob(spelling))
        except (ValueError, OSError):  # pragma: no cover - malformed pattern
            continue
        for match in matches:
            if match.is_file() and match not in seen:
                seen.add(match)
                yield match


def hash_paths(workspace: Path, patterns: list[str]) -> dict[str, str]:
    """Hash every file matching a list of glob patterns.

    Args:
        workspace: The workspace root that patterns are relative to.
        patterns: Globs such as ``"tests/security/**"`` or ``"attack/prompts.jsonl"``.

    Returns:
        Mapping of workspace-relative path to hex SHA-256, sorted by path.
    """
    hashes: dict[str, str] = {}
    for pattern in patterns:
        for match in iter_matching_files(workspace, pattern):
            hashes[str(match.relative_to(workspace))] = sha256_file(match)
    return dict(sorted(hashes.items()))


#: Status recorded for a baseline test that is no longer present in the report.
#: Deliberately not "passed": defaulting a vanished test to passing would make
#: deleting the tests you broke a way to dodge the regression cap.
MISSING_STATUS: Final[str] = "missing"


def _regressed_nodes(baseline: Baseline, results: dict[str, str]) -> list[str]:
    """Return the baseline-passing tests that no longer pass.

    A test counts as regressed if it now fails, errors, was skipped, **or is
    absent from the report entirely**.

    Args:
        baseline: The measured pre-fix state.
        results: Node id to status from the current run.

    Returns:
        The regressed node ids, in baseline order.
    """
    return [
        node
        for node in baseline.passing_nodes
        if results.get(node, MISSING_STATUS) != str(CheckStatus.PASSED)
    ]


#: Ways to neuter a test without editing its assertions. Detected separately from
#: file hashing because they can appear in config rather than in a protected file.
TAMPER_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    (r"@pytest\.mark\.skip", "a skip marker was added"),
    (r"@pytest\.mark\.xfail", "an xfail marker was added"),
    (r"^\s*addopts\s*=.*(-k|--deselect|--ignore)", "addopts was narrowed"),
    (r"^\s*collect_ignore", "collect_ignore was added"),
)


class CheckRunner:
    """Executes a list of :class:`Check` definitions against a workspace.

    Args:
        workspace: The scaffolded workspace directory.
        compose_project: ``COMPOSE_PROJECT_NAME`` for the exercise's containers.
        baseline: The measured pre-fix state, used to detect regressions.
        use_container: Run commands via ``docker compose exec`` when true. Set
            false only for templates that declare no services.
    """

    def __init__(
        self,
        workspace: Path,
        *,
        compose_project: str = "",
        baseline: Baseline | None = None,
        use_container: bool = True,
    ) -> None:
        self.workspace = Path(workspace)
        self.compose_project = compose_project
        self.baseline = baseline or Baseline()
        self.use_container = use_container
        #: Every command run, for the per-submission audit log.
        self.command_log: list[str] = []

    # -- command execution -------------------------------------------------

    def _wrap(self, shell_command: str, env: dict[str, str] | None = None) -> list[str]:
        """Build the argv that runs a shell command in the right place.

        Container-bound variables must be passed as ``-e`` flags. Setting them on the
        subprocess environment only configures the local ``docker`` CLI -- the process
        inside the container never sees them, which silently made ``CI_ENV`` a no-op for
        every containerised check.
        """
        if self.use_container and self.compose_project:
            argv = ["docker", "compose", "-p", self.compose_project, "exec", "-T"]
            for key, value in sorted((env or {}).items()):
                argv += ["-e", f"{key}={value}"]
            argv += [APP_SERVICE, "bash", "-lc", shell_command]
            return argv
        return ["bash", "-lc", shell_command]

    def run_command(
        self, shell_command: str, *, timeout: int | None = None, env: dict[str, str] | None = None
    ) -> tuple[int | None, str, int]:
        """Run a shell command in the workspace or its container.

        Args:
            shell_command: The command line to run.
            timeout: Seconds before the command is killed.
            env: Extra environment variables.

        Returns:
            ``(exit_code, combined_output, duration_ms)``. ``exit_code`` is
            ``None`` when the command timed out or could not be launched at all,
            which the caller must treat as indeterminate rather than failed.
        """
        argv = self._wrap(shell_command, env)
        limit = timeout if timeout is not None else settings.WORKSPACE_CHECK_TIMEOUT_SECONDS
        self.command_log.append(shell_command)

        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        started = time.perf_counter()
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, command is authored
                argv,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=limit,
                env=process_env,
                check=False,
                # Never inherit the caller's stdin. `docker compose exec -T` forwards
                # stdin into the container, so a check would otherwise consume whatever
                # the caller was reading -- silently eating the rest of a shell loop's
                # input -- or block forever on a pipe nobody is going to write to.
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            elapsed = int((time.perf_counter() - started) * 1000)
            return None, f"Command timed out after {limit}s: {shell_command}", elapsed
        except (OSError, FileNotFoundError) as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            return None, f"Could not run command: {exc}", elapsed

        elapsed = int((time.perf_counter() - started) * 1000)
        output = (completed.stdout or "") + (completed.stderr or "")
        return completed.returncode, output, elapsed

    # -- pytest ------------------------------------------------------------

    def run_pytest(
        self, selector: str = "", *, ci_env: bool = False, extra_args: str = ""
    ) -> tuple[dict[str, str], str, int | None, int]:
        """Run pytest and parse its JUnit report.

        Args:
            selector: A node id or path to run; empty runs the whole suite.
            ci_env: Apply the CI-shaped environment that makes flaky tests fail.
            extra_args: Additional pytest arguments.

        Returns:
            ``(results, raw_output, exit_code, duration_ms)`` where ``results``
            maps node id to status.
        """
        report_dir = self.workspace / GRADING_DIR
        report_dir.mkdir(parents=True, exist_ok=True)
        report_name = f"junit-{int(time.time() * 1000)}.xml"
        container_report = f"{GRADING_DIR}/{report_name}"

        command = (
            f"python -m pytest {selector} -p no:cacheprovider "
            f"--junitxml={container_report} {extra_args}".strip()
        )
        exit_code, output, elapsed = self.run_command(command, env=dict(CI_ENV) if ci_env else None)

        report_path = report_dir / report_name
        results: dict[str, str] = {}
        if report_path.exists():
            results = parse_junit(report_path.read_text(encoding="utf-8", errors="replace"))
            report_path.unlink(missing_ok=True)
        return results, output, exit_code, elapsed

    # -- individual check kinds --------------------------------------------

    def _check_pytest(self, check: Check, results: dict[str, str], output: str) -> CheckOutcome:
        """Evaluate a specific pytest node against a parsed report."""
        wanted = check.expect.get("status", str(CheckStatus.PASSED))
        matching = {
            node: status
            for node, status in results.items()
            if node == check.target or node.startswith(check.target)
        }
        if not matching:
            return self._outcome(
                check,
                CheckStatus.ERROR,
                expected=f"{check.target} {wanted}",
                actual="test was not collected or did not run",
                output=output,
            )
        failures = [node for node, status in matching.items() if status != wanted]
        status = CheckStatus.PASSED if not failures else CheckStatus.FAILED
        return self._outcome(
            check,
            status,
            expected=f"{len(matching)}/{len(matching)} {wanted}",
            actual=f"{len(matching) - len(failures)}/{len(matching)} {wanted}",
            output=output,
        )

    def _check_pytest_suite(
        self, check: Check, results: dict[str, str], output: str
    ) -> CheckOutcome:
        """Evaluate the whole suite against the authored baseline.

        Any test that passed before the change and fails now is a regression --
        the signal behind the regression grading cap.
        """
        if not results:
            return self._outcome(
                check,
                CheckStatus.ERROR,
                expected="suite runs",
                actual="no test results were produced",
                output=output,
            )
        broken = _regressed_nodes(self.baseline, results)
        status = CheckStatus.PASSED if not broken else CheckStatus.FAILED
        return self._outcome(
            check,
            status,
            expected=f"{len(self.baseline.passing_nodes)} baseline tests still pass",
            actual=f"{len(broken)} regressed" if broken else "no regressions",
            output=output,
        )

    def _check_file_unchanged(self, check: Check) -> tuple[CheckOutcome, list[str]]:
        """Verify protected files still match their recorded hashes."""
        expected: dict[str, str] = check.expect.get("hashes", {})
        actual = hash_paths(self.workspace, check.paths)

        changed = sorted(path for path, digest in expected.items() if actual.get(path) != digest)
        removed = sorted(path for path in expected if path not in actual)
        added = sorted(path for path in actual if path not in expected)

        # A test file that was edited *or deleted* is tampering; a brand-new test
        # file is legitimate (and is itself a stretch goal).
        offenders = sorted(set(changed) | set(removed))

        # Markers that neuter a test without changing a protected file.
        marker_hits: list[str] = []
        for path in actual:
            try:
                text = (self.workspace / path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for pattern, why in TAMPER_PATTERNS:
                if re.search(pattern, text, re.MULTILINE):
                    marker_hits.append(f"{path}: {why}")

        all_offenders = offenders + [hit.split(":", 1)[0] for hit in marker_hits]
        status = CheckStatus.PASSED if not all_offenders else CheckStatus.FAILED
        details = []
        if changed:
            details.append(f"modified: {changed}")
        if removed:
            details.append(f"deleted: {removed}")
        if marker_hits:
            details.extend(marker_hits)
        if added:
            details.append(f"new files (allowed): {added}")

        return (
            self._outcome(
                check,
                status,
                expected=f"{len(expected)} protected files unchanged",
                actual="; ".join(details) if details else "all unchanged",
            ),
            sorted(set(all_offenders)),
        )

    def _check_cmd(self, check: Check) -> CheckOutcome:
        """Run a command and compare its exit code."""
        wanted = int(check.expect.get("exit_code", 0))
        exit_code, output, elapsed = self.run_command(check.target)
        if exit_code is None:
            return self._outcome(
                check,
                CheckStatus.TIMEOUT,
                expected=f"exit {wanted}",
                actual="did not complete",
                output=output,
                duration_ms=elapsed,
            )
        status = CheckStatus.PASSED if exit_code == wanted else CheckStatus.FAILED
        return self._outcome(
            check,
            status,
            expected=f"exit {wanted}",
            actual=f"exit {exit_code}",
            output=output,
            duration_ms=elapsed,
        )

    def _check_grep(self, check: Check) -> CheckOutcome:
        """Search files for a pattern, in Python rather than shelling out.

        Done locally so it works whether or not containers are running, and so a
        missing ``grep`` or a BSD/GNU flag difference cannot change the verdict.
        """
        pattern = re.compile(check.target)
        searched = 0
        hits: list[str] = []
        for glob in check.paths or ["**/*.py"]:
            for candidate in sorted(self.workspace.glob(glob)):
                if not candidate.is_file():
                    continue
                searched += 1
                try:
                    text = candidate.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for number, line in enumerate(text.splitlines(), start=1):
                    if pattern.search(line):
                        hits.append(f"{candidate.relative_to(self.workspace)}:{number}")

        if searched == 0:
            return self._outcome(
                check,
                CheckStatus.ERROR,
                expected=f"files matching {check.paths}",
                actual="no files were searched",
            )

        want_present = check.kind == CheckKind.GREP_PRESENT
        found = bool(hits)
        status = CheckStatus.PASSED if found == want_present else CheckStatus.FAILED
        return self._outcome(
            check,
            status,
            expected=("pattern present" if want_present else "pattern absent"),
            actual=f"{len(hits)} match(es)" + (f": {hits[:5]}" if hits else ""),
        )

    def _compare_metric(self, value: float, op: str, threshold: float) -> bool:
        """Apply a comparison operator from an authored expectation."""
        comparisons = {
            "<=": value <= threshold,
            "<": value < threshold,
            ">=": value >= threshold,
            ">": value > threshold,
            "==": value == threshold,
        }
        if op not in comparisons:
            raise ValueError(f"unknown comparison operator {op!r}")
        return comparisons[op]

    def _check_metric(self, check: Check) -> tuple[CheckOutcome, dict[str, float]]:
        """Run a benchmark or eval script and compare a reported metric.

        The script prints a JSON object; the harness never parses human-readable
        output. For latency exercises the authored metric is a *work count* (SQL
        queries, HTTP calls, rows scanned) rather than wall-clock time, because a
        count has a 100x margin that laptop noise cannot cross.
        """
        metric_name = check.expect["metric"]
        op = check.expect["op"]
        threshold = float(check.expect["threshold"])

        exit_code, output, elapsed = self.run_command(check.target)
        if exit_code is None:
            return (
                self._outcome(
                    check,
                    CheckStatus.TIMEOUT,
                    expected=f"{metric_name} {op} {threshold}",
                    actual="script did not complete",
                    output=output,
                    duration_ms=elapsed,
                ),
                {},
            )

        payload: dict[str, Any] | None = None
        for line in reversed(output.splitlines()):
            stripped = line.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    payload = json.loads(stripped)
                    break
                except ValueError:
                    continue

        if payload is None or metric_name not in payload:
            return (
                self._outcome(
                    check,
                    CheckStatus.ERROR,
                    expected=f"{metric_name} {op} {threshold}",
                    actual=f"script emitted no JSON containing {metric_name!r}",
                    output=output,
                    duration_ms=elapsed,
                ),
                {},
            )

        value = float(payload[metric_name])
        passed = self._compare_metric(value, op, threshold)
        return (
            self._outcome(
                check,
                CheckStatus.PASSED if passed else CheckStatus.FAILED,
                expected=f"{metric_name} {op} {threshold}",
                actual=f"{metric_name} = {value}",
                output=output,
                duration_ms=elapsed,
            ),
            {
                key: float(val)
                for key, val in payload.items()
                if isinstance(val, (int, float)) and not isinstance(val, bool)
            },
        )

    def _check_flake_repeat(self, check: Check) -> CheckOutcome:
        """Run one test repeatedly under the CI environment.

        Reproducing flakiness is the hard part of a flaky-test exercise, so the
        bar is N consecutive passes, not one.
        """
        passes = 0
        last_output = ""
        for _ in range(check.repeat):
            results, output, _exit, _ms = self.run_pytest(check.target, ci_env=True)
            last_output = output
            statuses = [status for node, status in results.items() if node.startswith(check.target)]
            if statuses and all(status == str(CheckStatus.PASSED) for status in statuses):
                passes += 1
            else:
                break
        status = CheckStatus.PASSED if passes == check.repeat else CheckStatus.FAILED
        return self._outcome(
            check,
            status,
            expected=f"{check.repeat}/{check.repeat} passes under CI env",
            actual=f"{passes}/{check.repeat}",
            output=last_output,
        )

    def _outcome(
        self,
        check: Check,
        status: CheckStatus | str,
        *,
        expected: str = "",
        actual: str = "",
        output: str = "",
        duration_ms: int = 0,
    ) -> CheckOutcome:
        """Build a :class:`CheckOutcome` for a check."""
        return CheckOutcome(
            check_id=check.id,
            kind=str(check.kind),
            status=str(status),
            passed=str(status) == str(CheckStatus.PASSED),
            weight=check.weight,
            required=check.required,
            stretch=check.stretch,
            expected=expected,
            actual=actual,
            duration_ms=duration_ms,
            output=_truncate(output),
            description=check.description,
        )

    # -- orchestration -----------------------------------------------------

    def run_all(self, checks: list[Check]) -> CheckRunSummary:
        """Run every check and aggregate the objective signal.

        The suite is run at most once and its report reused across all pytest-node
        checks, rather than re-running pytest per assertion.

        Args:
            checks: The exercise's authored checks. ``llm`` checks are skipped
                here; they are answered by the evaluator.

        Returns:
            A :class:`CheckRunSummary`.
        """
        summary = CheckRunSummary()

        needs_suite = any(
            check.kind in {CheckKind.PYTEST, CheckKind.PYTEST_SUITE} for check in checks
        )
        results: dict[str, str] = {}
        suite_output = ""
        if needs_suite:
            results, suite_output, _exit, _ms = self.run_pytest()
            if not results:
                summary.notes.append(
                    "pytest produced no parseable report; test-based checks are "
                    "indeterminate rather than failed"
                )

        for check in checks:
            try:
                if check.kind == CheckKind.LLM:
                    summary.outcomes.append(
                        self._outcome(
                            check,
                            CheckStatus.SKIPPED,
                            expected="model judgment",
                            actual="delegated to the evaluator",
                        )
                    )
                elif check.kind == CheckKind.PYTEST:
                    summary.outcomes.append(self._check_pytest(check, results, suite_output))
                elif check.kind == CheckKind.PYTEST_SUITE:
                    outcome = self._check_pytest_suite(check, results, suite_output)
                    summary.outcomes.append(outcome)
                    summary.regressions = _regressed_nodes(self.baseline, results)
                elif check.kind == CheckKind.FILE_UNCHANGED:
                    outcome, offenders = self._check_file_unchanged(check)
                    summary.outcomes.append(outcome)
                    summary.tampered_paths.extend(offenders)
                elif check.kind == CheckKind.CMD:
                    summary.outcomes.append(self._check_cmd(check))
                elif check.kind in {CheckKind.GREP_ABSENT, CheckKind.GREP_PRESENT}:
                    summary.outcomes.append(self._check_grep(check))
                elif check.kind in {CheckKind.BENCHMARK, CheckKind.METRIC}:
                    outcome, metrics = self._check_metric(check)
                    summary.outcomes.append(outcome)
                    summary.metrics.update(metrics)
                elif check.kind == CheckKind.FLAKE_REPEAT:
                    summary.outcomes.append(self._check_flake_repeat(check))
                else:  # pragma: no cover - the enum is exhaustive above
                    summary.outcomes.append(
                        self._outcome(
                            check, CheckStatus.ERROR, actual=f"unsupported kind {check.kind}"
                        )
                    )
            except Exception as exc:  # noqa: BLE001 - one bad check must not void the run
                logger.exception("check %s raised", check.id)
                summary.outcomes.append(
                    self._outcome(check, CheckStatus.ERROR, actual=f"harness error: {exc}")
                )

        summary.tampered_paths = sorted(set(summary.tampered_paths))
        return summary


def record_protected_hashes(workspace: Path, patterns: list[str]) -> dict[str, str]:
    """Record the hashes of protected files at scaffold time.

    The recorded values become the ``expect.hashes`` of the exercise's
    ``file_unchanged`` check, which is what makes test tampering detectable.

    Args:
        workspace: The freshly scaffolded workspace.
        patterns: Globs naming the files to protect.

    Returns:
        Mapping of workspace-relative path to hex SHA-256.
    """
    return hash_paths(workspace, patterns)
