"""Measure an exercise's pre-fix baseline and prove it is solvable.

Two phases, which answer two different questions:

**pre** — scaffold with the mutation applied and record exactly which tests fail. The
baseline is *measured*, never authored: a hand-written failing set makes the regression
check meaningless, and a mutation that breaks more than intended is an unfair exercise
that only a measurement will catch. ``--write`` stores the result in
``catalog/baselines.json``.

**post** — apply ``reference.patch`` and run every check. This is the only thing that
proves the exercise is solvable at all, that the authored thresholds are achievable, and
that it can be solved *without* touching a protected file. An exercise whose post phase
has never run is a guess.

This is a subset of the ``verify_workspace_exercises`` the plan describes — the phases
that authoring an exercise cannot be done honestly without. Static validation (V0),
history shape (V1) and the grading smoke test (V5) are not implemented here.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.workspace.calibration.runner import calibration_user, harness_setup_commands
from apps.workspace.models import WorkspaceExercise, WorkspaceSession
from apps.workspace.schemas import Baseline
from apps.workspace.services import docker_env, git_ops, manifest, paths, scaffolder
from apps.workspace.services.check_runner import CheckRunner
from apps.workspace.services.submission import _checks_for

#: Relative to the catalog package.
BASELINES_PATH = Path("apps/workspace/catalog/baselines.json")


class Command(BaseCommand):
    """Measure baselines and verify reference solutions."""

    help = "Measure an exercise's pre-fix baseline and prove reference.patch solves it."

    def add_arguments(self, parser) -> None:
        """Register the filters and phase selection."""
        parser.add_argument("--only", default="", help="Limit to one exercise slug or prefix")
        parser.add_argument(
            "--phase",
            choices=["pre", "post", "both"],
            default="both",
            help="Which phase to run (default both)",
        )
        parser.add_argument(
            "--write",
            action="store_true",
            help="Write the measured baseline into catalog/baselines.json",
        )
        parser.add_argument(
            "--repeat-suite",
            type=int,
            default=1,
            help=(
                "Run the pre-fix suite this many times and union the failures. Use >1 "
                "for an exercise whose defect is nondeterministic, where a single run "
                "cannot see the whole failing set."
            ),
        )

    def handle(self, *args, **options) -> None:
        """Verify each selected exercise."""
        exercises = WorkspaceExercise.objects.order_by("exercise_number")
        if options["only"]:
            exercises = exercises.filter(slug__startswith=options["only"])
        if not exercises:
            raise CommandError(f"no exercises match {options['only']!r}")

        measured: dict[str, dict] = {}
        failures: list[str] = []

        for exercise in exercises:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{exercise.slug}"))
            try:
                result = self._verify(exercise, options)
            except Exception as exc:  # noqa: BLE001 - reported per exercise, never fatal
                self.stdout.write(self.style.ERROR(f"  FAILED: {exc}"))
                failures.append(f"{exercise.slug}: {exc}")
                continue
            if result.get("baseline"):
                measured[exercise.slug] = result["baseline"]
            failures.extend(result.get("problems", []))

        if options["write"] and measured:
            self._write_baselines(measured)

        self.stdout.write("")
        if failures:
            self.stdout.write(self.style.ERROR(f"{len(failures)} problem(s):"))
            for problem in failures:
                self.stdout.write(f"  - {problem}")
            raise CommandError("verification failed")
        self.stdout.write(self.style.SUCCESS("All selected exercises verified."))

    # -- one exercise -----------------------------------------------------

    def _verify(self, exercise: WorkspaceExercise, options: dict) -> dict:
        """Scaffold, measure, and optionally verify the reference patch."""
        out: dict = {"problems": []}

        WorkspaceSession.objects.filter(
            user=calibration_user(),
            exercise=exercise,
            status__in=WorkspaceSession.ACTIVE_STATUSES,
        ).update(status=WorkspaceSession.Status.ABANDONED)

        session = WorkspaceSession.objects.create(
            user=calibration_user(),
            exercise=exercise,
            exercise_type=exercise.exercise_type,
            difficulty=exercise.difficulty,
            time_limit_seconds=exercise.time_limit_seconds,
        )
        try:
            scaffold = scaffolder.scaffold(session)
            if not scaffold.ok:
                raise CommandError(f"scaffold failed: {scaffold.error}")
            workspace = Path(session.workspace_path)
            self.stdout.write(f"  scaffolded {workspace.name}")

            if exercise.needs_docker:
                ok, output = scaffolder.start_containers(session)
                if not ok:
                    raise CommandError(f"containers did not come up: {output[-800:]}")
                runner = self._runner(session)
                for command in harness_setup_commands(exercise):
                    code, setup_output, _ = runner.run_command(command)
                    if code != 0:
                        raise CommandError(f"{command} failed: {setup_output[-800:]}")
                self.stdout.write("  containers up, setup commands run")

            baseline = None
            if options["phase"] in {"pre", "both"}:
                baseline = self._measure(session, repeats=options["repeat_suite"])
                problems, metrics = self._assert_defect_is_detected(session, exercise, baseline)
                out["problems"] += problems
                baseline = baseline.model_copy(update={"metrics": metrics})
                out["baseline"] = {
                    "failing_nodes": baseline.failing_nodes,
                    "passing_nodes": baseline.passing_nodes,
                    "metrics": baseline.metrics,
                }

            if options["phase"] in {"post", "both"}:
                stored = Baseline.model_validate((exercise.grading_spec or {}).get("baseline", {}))
                out["problems"] += self._verify_reference(
                    session, exercise, baseline=baseline or stored
                )
        finally:
            if session.compose_project:
                docker_env.compose_down(
                    session.compose_project, Path(session.workspace_path or ".")
                )
            session.end_session(WorkspaceSession.EndReason.ABANDONED)

        return out

    def _runner(self, session: WorkspaceSession, baseline: Baseline | None = None) -> CheckRunner:
        """Build a CheckRunner bound to a session's workspace and container."""
        return CheckRunner(
            Path(session.workspace_path),
            compose_project=session.compose_project,
            baseline=baseline,
            use_container=bool(session.compose_project),
        )

    # -- pre phase --------------------------------------------------------

    def _measure(self, session: WorkspaceSession, *, repeats: int) -> Baseline:
        """Run the suite and record which nodes fail.

        A node that fails in *any* run is recorded as failing and kept out of
        ``passing_nodes``. That is what makes a nondeterministic defect safe to baseline:
        ``_regressed_nodes`` only ever looks at ``passing_nodes``, so a flaky node listed
        nowhere can never be reported to a candidate as a regression they caused.
        """
        runner = self._runner(session)
        ever_failed: set[str] = set()
        seen: set[str] = set()

        for attempt in range(repeats):
            results, output, exit_code, _ms = runner.run_pytest("", ci_env=True)
            if not results:
                raise CommandError(
                    f"suite produced no junit results (exit {exit_code}):\n{output[-1500:]}"
                )
            seen |= set(results)
            ever_failed |= {node for node, status in results.items() if status != "passed"}
            self.stdout.write(
                f"  suite run {attempt + 1}/{repeats}: "
                f"{len(results)} tests, {len(ever_failed)} failing so far"
            )

        failing = sorted(ever_failed)
        passing = sorted(seen - ever_failed)
        self.stdout.write(f"  measured: {len(failing)} failing, {len(passing)} passing")
        for node in failing:
            self.stdout.write(f"    FAIL {node}")
        return Baseline(failing_nodes=failing, passing_nodes=passing)

    def _assert_defect_is_detected(
        self, session: WorkspaceSession, exercise: WorkspaceExercise, baseline: Baseline
    ) -> tuple[list[str], dict[str, float]]:
        """Run every check *before* the fix and assert the exercise is not already solved.

        A mutation that no check notices is not an exercise: the candidate would be
        graded on work nobody asked for, and the reference patch would appear to fix
        something that was never broken. This is the assertion that catches an authored
        check whose target does not match, a threshold set on the wrong side of the
        measurement, or a mutation that simply does not bite.

        Also returns the pre-fix metrics, which are what the authored thresholds have to
        sit between. The post phase prints the post-fix values, so the two together show
        whether a threshold has real margin or is balanced on a knife edge.
        """
        runner = self._runner(session, baseline=baseline)
        summary = runner.run_all(_checks_for(exercise))

        failed_required = [o.check_id for o in summary.required_outcomes if not o.passed]
        self.stdout.write(
            f"  pre-fix checks: {len(failed_required)} of "
            f"{len(summary.required_outcomes)} required failing "
            f"({', '.join(failed_required) or 'none'})"
        )
        if summary.metrics:
            self.stdout.write(f"    pre-fix metrics: {json.dumps(summary.metrics)}")

        problems: list[str] = []
        if not failed_required:
            problems.append(
                f"{exercise.slug}: every required check PASSES before the fix, so the "
                "mutation is not detected by anything -- the exercise is already solved"
            )
        return problems, summary.metrics

    # -- post phase -------------------------------------------------------

    def _verify_reference(
        self, session: WorkspaceSession, exercise: WorkspaceExercise, *, baseline: Baseline
    ) -> list[str]:
        """Apply reference.patch, run every check, and report what did not hold."""
        patch = paths.template_root() / manifest.PATCHES_DIRNAME / exercise.slug / "reference.patch"
        if not patch.is_file():
            return [f"{exercise.slug}: no reference.patch -- solvability is unproven"]

        workspace = Path(session.workspace_path)
        git_ops.run_git(workspace, "apply", "--whitespace=nowarn", str(patch))
        self.stdout.write("  applied reference.patch")

        runner = self._runner(session, baseline=baseline)
        summary = runner.run_all(_checks_for(exercise))

        problems: list[str] = []
        for outcome in summary.outcomes:
            mark = "ok  " if outcome.passed else "FAIL"
            if outcome.kind == "llm":
                mark = "skip"
            self.stdout.write(
                f"    {mark} {outcome.check_id} {outcome.kind} "
                f"{'required' if outcome.required else 'stretch'} :: {outcome.actual[:70]}"
            )
            if outcome.required and not outcome.passed:
                problems.append(
                    f"{exercise.slug}: required check {outcome.check_id} does not pass "
                    f"under the reference solution ({outcome.actual[:120]})"
                )

        if summary.regressions:
            problems.append(
                f"{exercise.slug}: reference solution regresses {len(summary.regressions)} "
                f"baseline-passing test(s): {summary.regressions[:5]}"
            )
        if summary.tampering_detected:
            problems.append(
                f"{exercise.slug}: reference solution modifies protected files "
                f"{summary.tampered_paths} -- the exercise is not solvable without tampering"
            )
        if summary.metrics:
            self.stdout.write(f"    metrics: {json.dumps(summary.metrics)}")
        return problems

    # -- persistence ------------------------------------------------------

    def _write_baselines(self, measured: dict[str, dict]) -> None:
        """Merge measured baselines into the catalog's baselines.json."""
        path = BASELINES_PATH
        existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        existing.update(measured)
        path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"\nWrote {len(measured)} baseline(s) to {path}. "
                "Re-run seed_workspace_exercises to load them."
            )
        )
