"""Load the authored exercise catalog into the database.

Validates every entry against :class:`~apps.workspace.schemas.AuthoredExercise`
before writing anything, so a malformed exercise fails loudly here rather than
surfacing as a broken scaffold while someone is on the clock.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from pydantic import ValidationError

from apps.workspace.catalog import EXERCISES
from apps.workspace.catalog.hashing import mutation_digest, tree_checksum
from apps.workspace.models import WorkspaceExercise
from apps.workspace.schemas import AuthoredExercise
from apps.workspace.services import manifest, paths


class Command(BaseCommand):
    """Upsert authored exercises by slug."""

    help = "Validate and load the workspace exercise catalog."

    def add_arguments(self, parser) -> None:
        """Register command arguments."""
        parser.add_argument("--slug", help="Load only this exercise.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate everything and report, without writing to the database.",
        )

    def handle(self, *args, **options) -> None:
        """Validate and load the catalog."""
        wanted = options.get("slug")
        entries = [e for e in EXERCISES if not wanted or e.get("slug") == wanted]
        if not entries:
            raise CommandError(f"No exercise matches slug {wanted!r}")

        validated: list[AuthoredExercise] = []
        problems: list[str] = []
        for raw in entries:
            try:
                validated.append(AuthoredExercise.model_validate(raw))
            except ValidationError as exc:
                problems.append(f"{raw.get('slug', '<no slug>')}:\n{exc}")

        if problems:
            for problem in problems:
                self.stderr.write(self.style.ERROR(problem))
            raise CommandError(f"{len(problems)} exercise(s) failed validation.")

        # Templates are validated too: a manifest that does not match its tree would
        # only fail later, during someone's attempt.
        for exercise in validated:
            for issue in manifest.validate_template(exercise.base_app):
                problems.append(issue)
        if problems:
            for problem in sorted(set(problems)):
                self.stderr.write(self.style.ERROR(problem))
            raise CommandError("Template validation failed.")

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(f"{len(validated)} exercise(s) valid. Nothing written.")
            )
            return

        created = updated = 0
        for exercise in validated:
            template_name = exercise.base_app
            patch_dir = paths.template_root() / manifest.PATCHES_DIRNAME / exercise.slug
            patches = [
                patch_dir / step["patch"]
                for step in exercise.mutations
                if step.get("op") == "apply_patch"
            ]

            spec = {
                "checks": [check.model_dump(mode="json") for check in exercise.checks],
                "baseline": exercise.baseline.model_dump(mode="json"),
                "context_excerpts": [e.model_dump(mode="json") for e in exercise.context_excerpts],
                "mutation_digest": mutation_digest(patches),
            }

            _obj, was_created = WorkspaceExercise.objects.update_or_create(
                slug=exercise.slug,
                defaults={
                    "exercise_number": exercise.exercise_number,
                    "title": exercise.title,
                    "exercise_type": exercise.exercise_type,
                    "base_app": exercise.base_app,
                    "difficulty": exercise.difficulty,
                    "defect_class": exercise.defect_class,
                    "brief_md": exercise.brief_md,
                    "definition_of_done": exercise.definition_of_done,
                    "time_limit_seconds": exercise.time_limit_minutes * 60,
                    "expected_time_minutes": exercise.expected_time_minutes,
                    "focus_paths": exercise.focus_paths,
                    "protected_paths": exercise.protected_paths,
                    "mutations": exercise.mutations,
                    "grading_spec": spec,
                    "grading_notes": exercise.grading_notes,
                    "context_excerpts": [
                        e.model_dump(mode="json") for e in exercise.context_excerpts
                    ],
                    "hints": exercise.hints,
                    "databases": list(exercise.databases),
                    "needs_docker": exercise.needs_docker,
                    "template_dir": template_name,
                    "template_checksum": tree_checksum(Path(manifest.template_dir(template_name))),
                    "tags": exercise.tags,
                    "is_active": True,
                },
            )
            created += was_created
            updated += not was_created
            self.stdout.write(f"  {'created' if was_created else 'updated'}  {exercise.slug}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(validated)} exercise(s): {created} created, {updated} updated."
            )
        )
