"""Management command for importing questions from exported JSON files."""

import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.questions.models import Question
from apps.subjects.models import Subject


class Command(BaseCommand):
    """Import questions from JSON export files (created by export_questions)."""

    help = (
        "Import questions from JSON files exported by export_questions command. "
        "Use this to restore questions or sync between environments."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "input_file",
            type=str,
            nargs="?",
            default=None,
            help="JSON file to import",
        )
        parser.add_argument(
            "--input-dir",
            "-d",
            type=str,
            default=None,
            help="Import all JSON files from directory",
        )
        parser.add_argument(
            "--subject",
            "-s",
            type=str,
            default=None,
            help="Override the subject slug from the file",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update existing questions instead of skipping",
        )

    def handle(self, *args, **options):
        if options["input_dir"]:
            input_dir = Path(options["input_dir"])
            if not input_dir.exists():
                raise CommandError(f"Directory not found: {input_dir}")

            json_files = list(input_dir.glob("*.json"))
            if not json_files:
                raise CommandError(f"No JSON files found in {input_dir}")

            total_imported = 0
            total_skipped = 0
            for json_file in json_files:
                imported, skipped = self._import_file(json_file, options)
                total_imported += imported
                total_skipped += skipped

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nTotal: Imported {total_imported}, skipped {total_skipped} questions"
                )
            )

        elif options["input_file"]:
            input_path = Path(options["input_file"])
            if not input_path.exists():
                raise CommandError(f"File not found: {input_path}")

            imported, skipped = self._import_file(input_path, options)
            self.stdout.write(
                self.style.SUCCESS(f"\nImported {imported}, skipped {skipped} questions")
            )
        else:
            raise CommandError("Specify an input_file or use --input-dir")

    def _import_file(self, file_path, options):
        """Import questions from a single JSON file."""
        self.stdout.write(f"\nImporting from: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f"  Invalid JSON: {e}"))
            return 0, 0

        # Validate format
        if "metadata" not in data or "questions" not in data:
            self.stdout.write(
                self.style.ERROR("  Invalid format: missing metadata or questions")
            )
            return 0, 0

        # Get subject
        subject_slug = options["subject"] or data["metadata"].get("subject_slug")
        if not subject_slug:
            self.stdout.write(self.style.ERROR("  No subject specified"))
            return 0, 0

        try:
            subject = Subject.objects.get(slug=subject_slug)
        except Subject.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"  Subject not found: {subject_slug}"))
            return 0, 0

        self.stdout.write(f"  Subject: {subject.name}")
        self.stdout.write(f"  Questions in file: {len(data['questions'])}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("  DRY RUN - no changes made"))
            return len(data["questions"]), 0

        imported = 0
        skipped = 0
        updated = 0

        for q_data in data["questions"]:
            # Generate hash for deduplication
            content = f"{subject.id}:{q_data['question_text']}:{q_data['correct_answer']}"
            source_hash = hashlib.sha256(content.encode()).hexdigest()

            # Check for existing
            existing = Question.objects.filter(source_hash=source_hash).first()

            if existing:
                if options["update_existing"]:
                    # Update existing question
                    existing.question_text = q_data["question_text"]
                    existing.question_type = q_data.get("question_type", "mc")
                    existing.options = q_data.get("options", [])
                    existing.correct_answer = q_data["correct_answer"]
                    existing.explanation = q_data.get("explanation", "")
                    existing.difficulty = q_data.get("difficulty", "intermediate")
                    existing.tags = q_data.get("tags", [])
                    existing.is_active = q_data.get("is_active", True)
                    existing.save()
                    updated += 1
                else:
                    skipped += 1
                continue

            # Create new question
            Question.objects.create(
                subject=subject,
                question_text=q_data["question_text"],
                question_type=q_data.get("question_type", "mc"),
                options=q_data.get("options", []),
                correct_answer=q_data["correct_answer"],
                explanation=q_data.get("explanation", ""),
                difficulty=q_data.get("difficulty", "intermediate"),
                tags=q_data.get("tags", []),
                source=q_data.get("source", Question.Source.MANUAL),
                is_active=q_data.get("is_active", True),
                source_hash=source_hash,
            )
            imported += 1

        self.stdout.write(
            f"  Results: {imported} imported, {skipped} skipped, {updated} updated"
        )

        return imported, skipped
