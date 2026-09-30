"""Run a blind rubric-calibration round.

Four actions, in the order they are meant to be used::

    manage.py calibrate_workspace build    # scaffold, replay, grade (slow, costs API)
    manage.py calibrate_workspace packet   # write blind packets + a fresh scoresheet
    # ... you fill in calibration/scoresheet.md by hand ...
    manage.py calibrate_workspace report   # reveal and compare
    manage.py calibrate_workspace status   # what has been built, what is outstanding

``build`` and ``packet`` are separate on purpose: building is slow and hits the Claude
API, so re-rendering packets after an accidental deletion must not require regrading.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.workspace.calibration import packets, report, store
from apps.workspace.calibration.personas import all_personas, personas_for
from apps.workspace.calibration.runner import build as build_persona
from apps.workspace.calibration.spec import Persona
from apps.workspace.models import WorkspaceGrade, WorkspaceSession


class Command(BaseCommand):
    """Build, present and score a calibration round."""

    help = "Grade known-quality submissions and compare against hand-assigned letters."

    def add_arguments(self, parser) -> None:
        """Register the action and its filters."""
        parser.add_argument(
            "action",
            choices=["build", "packet", "report", "status", "recompute"],
            help="Which step of the round to run",
        )
        parser.add_argument(
            "--exercise",
            default="",
            help="Limit to one exercise slug, or a unique prefix of one",
        )
        parser.add_argument(
            "--persona",
            default="",
            help="Limit to one persona id within the chosen exercise",
        )
        parser.add_argument(
            "--save",
            action="store_true",
            help="report: append this round to calibration/grades.json",
        )
        parser.add_argument(
            "--keep-containers",
            action="store_true",
            help="build: leave each exercise's containers running afterwards",
        )

    # -- selection --------------------------------------------------------

    def _selected(self, options: dict) -> list[Persona]:
        """Resolve the --exercise/--persona filters to a persona list.

        Raises:
            CommandError: If the filters match nothing, so a typo cannot masquerade
                as "there was nothing to do".
        """
        chosen = all_personas()
        wanted = options["exercise"]
        if wanted:
            matches = [p for p in chosen if p.exercise_slug.startswith(wanted)]
            if not matches:
                slugs = sorted({p.exercise_slug for p in chosen})
                raise CommandError(f"no personas for {wanted!r}. Known: {', '.join(slugs)}")
            chosen = matches
        if options["persona"]:
            chosen = [p for p in chosen if p.persona_id == options["persona"]]
            if not chosen:
                raise CommandError(f"no persona with id {options['persona']!r}")
        return chosen

    def handle(self, *args, **options) -> None:
        """Dispatch to the chosen action."""
        action = options["action"]
        if action == "build":
            self._build(options)
        elif action == "packet":
            self._packet(options)
        elif action == "report":
            self._report(options)
        elif action == "recompute":
            self._recompute(options)
        else:
            self._status(options)

    # -- recompute --------------------------------------------------------

    def _recompute(self, options: dict) -> None:
        """Re-derive every recorded letter under the current weights, with no API call.

        For a weight change. Dimension scores are the model's judgment and are unaffected
        by the weights, so re-running the model would only add sampling noise and make
        the before/after impossible to read.
        """
        from apps.workspace.grading import DimensionScores, regrade_with_recorded_caps
        from apps.workspace.services.exercise_evaluator import RUBRIC_VERSION

        entries = store.read_answer_key()
        graded = [entry for entry in entries if entry.graded]
        if not graded:
            raise CommandError("no graded items to recompute")

        moved = 0
        for entry in graded:
            scores = entry.system_dimensions or {}
            if not scores:
                self.stdout.write(self.style.WARNING(f"  {entry.item} has no dimensions; skipped"))
                continue
            outcome = regrade_with_recorded_caps(
                DimensionScores(
                    correctness=scores.get("correctness", 0),
                    engineering=scores.get("engineering", 0),
                    documentation=scores.get("documentation", 0),
                    completeness=scores.get("completeness", 0),
                ),
                list(entry.applied_caps or []),
            )
            before = f"{entry.system_letter} {entry.system_score}"
            after = f"{outcome.letter} {outcome.score}"
            changed = outcome.letter != entry.system_letter or outcome.score != entry.system_score
            moved += changed

            grade_row = WorkspaceGrade.objects.filter(session_id=entry.session_id).first()
            if grade_row:
                grade_row.overall_score = outcome.score
                grade_row.base_score = outcome.base_score
                grade_row.letter_grade = outcome.letter
                grade_row.uncapped_letter = outcome.uncapped_letter
                grade_row.grade_points = outcome.grade_points
                grade_row.rubric_version = RUBRIC_VERSION
                grade_row.save(
                    update_fields=[
                        "overall_score",
                        "base_score",
                        "letter_grade",
                        "uncapped_letter",
                        "grade_points",
                        "rubric_version",
                    ]
                )
            entry.system_letter = outcome.letter
            entry.system_score = outcome.score

            marker = "  ->" if changed else "    "
            self.stdout.write(
                f"{marker} {entry.item}  {entry.persona_id:<16}{before:>8} -> {after}"
            )

        store.write_answer_key(entries)
        self.stdout.write(
            self.style.SUCCESS(
                f"\nRecomputed {len(graded)} grade(s) under {RUBRIC_VERSION}; "
                f"{moved} changed. Dimension scores untouched, no API calls made."
            )
        )

    # -- build ------------------------------------------------------------

    def _build(self, options: dict) -> None:
        """Scaffold, replay and grade each selected persona."""
        selected = self._selected(options)
        store.assert_unique_item_ids([p.key for p in selected])

        self.stdout.write(
            f"Building {len(selected)} persona(s). Each one scaffolds a workspace, "
            "starts containers, runs the real acceptance checks and makes one Claude "
            "call, so expect a few minutes each."
        )

        existing = {entry.persona_key: entry for entry in store.read_answer_key()}
        by_exercise: dict[str, list[Persona]] = {}
        for persona in selected:
            by_exercise.setdefault(persona.exercise_slug, []).append(persona)

        for slug, group in by_exercise.items():
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{slug}"))
            for persona in group:
                self.stdout.write(f"  {persona.persona_id}: {persona.tier}")
                # Always torn down between personas unless explicitly asked otherwise.
                # Keeping them up buys nothing: every persona scaffolds its own
                # workspace and its own Compose project (the name carries the session
                # id), so nothing is reused except the Docker image cache, which
                # survives teardown anyway. Leaving them up just strands two containers
                # and a port pair per persona.
                result = build_persona(persona, keep_containers=options["keep_containers"])
                entry = self._entry_for(persona, result)
                existing[persona.key] = entry
                if result.ok:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"    -> {entry.system_letter} ({entry.system_score}) as {entry.item}"
                        )
                    )
                else:
                    self.stdout.write(self.style.ERROR(f"    -> FAILED: {result.error}"))
                    for line in result.log or []:
                        self.stdout.write(f"       {line}")

        path = store.write_answer_key(sorted(existing.values(), key=lambda e: e.persona_key))
        graded = sum(1 for entry in existing.values() if entry.graded)
        self.stdout.write(
            f"\nWrote {path} ({graded}/{len(existing)} graded). "
            "Do not read it. Next: manage.py calibrate_workspace packet"
        )

    def _entry_for(self, persona: Persona, result) -> store.AnswerKeyEntry:
        """Build the answer-key entry for a finished build."""
        grade = result.grade
        session = result.session
        entry = store.AnswerKeyEntry(
            item=store.item_id(persona.key),
            persona_key=persona.key,
            exercise_slug=persona.exercise_slug,
            persona_id=persona.persona_id,
            tier=persona.tier,
            rationale=persona.rationale,
            predicted_letter=persona.predicted_letter,
            session_id=session.pk if session else 0,
            built_at=timezone.now().isoformat(),
            error=result.error,
        )
        if grade:
            submission = getattr(session, "submission", None)
            required = (
                [row for row in submission.check_results.all() if row.required]
                if submission
                else []
            )
            entry.system_letter = grade.letter_grade
            entry.system_score = grade.overall_score
            entry.system_dimensions = grade.dimension_scores or {}
            entry.applied_caps = list(grade.applied_caps or [])
            entry.symptom_patch_suspected = grade.symptom_patch_suspected
            entry.objective_status = grade.objective_status
            entry.required_passed = f"{sum(1 for r in required if r.passed)}/{len(required)}"
            entry.degraded = grade.evaluation_degraded
        return entry

    # -- packet -----------------------------------------------------------

    def _packet(self, options: dict) -> None:
        """Render blind packets and a scoresheet for every graded item."""
        entries = [entry for entry in store.read_answer_key() if entry.graded]
        if not entries:
            raise CommandError(
                "no graded items; run `calibrate_workspace build` first "
                f"(answer key: {store.answer_key_path()})"
            )
        if options["exercise"]:
            entries = [e for e in entries if e.exercise_slug.startswith(options["exercise"])]

        # Packet order is by item id, which is a hash -- so the reading order carries
        # no hint of tier, and the strong submission is as likely to be first as last.
        entries.sort(key=lambda entry: entry.item)

        written = []
        for entry in entries:
            session = WorkspaceSession.objects.get(pk=entry.session_id)
            packet = packets.render(session, entry.persona_key)
            written.append(packets.write(packet))
            self.stdout.write(f"  {packet.item}  {packet.char_count:>7,} chars")

        sheet_path = store.scoresheet_path()
        existing = (
            store.parse_scoresheet(sheet_path.read_text(encoding="utf-8"))
            if sheet_path.is_file()
            else {}
        )
        sheet_path.parent.mkdir(parents=True, exist_ok=True)
        sheet_path.write_text(
            store.render_scoresheet([e.item for e in entries], existing=existing),
            encoding="utf-8",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{len(written)} packet(s) in {store.packets_dir()}\n"
                f"Scoresheet: {sheet_path}\n\n"
                "Read each packet, record a letter in the scoresheet, then run:\n"
                "  manage.py calibrate_workspace report --save"
            )
        )

    # -- report -----------------------------------------------------------

    def _report(self, options: dict) -> None:
        """Reveal the system's grades and compare against the scoresheet."""
        round_ = report.build_round()
        self.stdout.write(report.render(round_))
        if options["save"] and round_.comparisons:
            self.stdout.write(f"Appended this round to {report.archive(round_)}")

    # -- status -----------------------------------------------------------

    def _status(self, options: dict) -> None:
        """Summarise what is authored, built and graded."""
        entries = {entry.persona_key: entry for entry in store.read_answer_key()}
        sheet_path = store.scoresheet_path()
        grades = (
            store.parse_scoresheet(sheet_path.read_text(encoding="utf-8"))
            if sheet_path.is_file()
            else {}
        )

        slugs = sorted({p.exercise_slug for p in all_personas()})
        self.stdout.write(
            f"{len(all_personas())} persona(s) authored across {len(slugs)} exercise(s)\n"
        )
        for slug in slugs:
            self.stdout.write(self.style.MIGRATE_HEADING(slug))
            for persona in personas_for(slug):
                entry = entries.get(persona.key)
                item = store.item_id(persona.key)
                if entry is None:
                    state = "not built"
                elif not entry.graded:
                    state = f"build failed: {entry.error[:60]}"
                else:
                    human = grades.get(item)
                    state = (
                        "graded, awaiting your letter"
                        if human is None or not human.filled
                        else f"you said {human.letter}"
                    )
                self.stdout.write(f"  {item}  {persona.persona_id:<12} {state}")
        self.stdout.write("")
