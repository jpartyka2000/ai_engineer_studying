"""Management command for exporting questions to version-controlled files."""

import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.questions.models import Question
from apps.subjects.models import Subject


class Command(BaseCommand):
    """Export questions to JSON or SQL files for version control."""

    help = (
        "Export questions to JSON or SQL files. "
        "JSON format is recommended for Git version control."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "subject_slug",
            type=str,
            nargs="?",
            default=None,
            help="Subject slug to export (omit for all subjects)",
        )
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            default=None,
            help="Output file path (default: questions/<subject>.json)",
        )
        parser.add_argument(
            "--format",
            "-f",
            choices=["json", "sql"],
            default="json",
            help="Output format (default: json)",
        )
        parser.add_argument(
            "--output-dir",
            "-d",
            type=str,
            default="questions",
            help="Output directory for exports (default: questions)",
        )
        parser.add_argument(
            "--all",
            "-a",
            action="store_true",
            help="Export all subjects to separate files",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Include inactive questions in export",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        if options["all"]:
            # Export all subjects
            subjects = Subject.objects.filter(is_active=True)
            for subject in subjects:
                self._export_subject(subject, output_dir, options)
            self.stdout.write(
                self.style.SUCCESS(f"\nExported {subjects.count()} subjects to {output_dir}/")
            )
        elif options["subject_slug"]:
            # Export single subject
            try:
                subject = Subject.objects.get(slug=options["subject_slug"])
            except Subject.DoesNotExist:
                raise CommandError(f"Subject '{options['subject_slug']}' not found")

            output_path = options["output"]
            if not output_path:
                ext = options["format"]
                output_path = output_dir / f"{subject.slug}.{ext}"

            self._export_subject(subject, output_dir, options, output_path)
        else:
            raise CommandError("Specify a subject_slug or use --all to export all subjects")

    def _export_subject(self, subject, output_dir, options, output_path=None):
        """Export a single subject's questions."""
        fmt = options["format"]

        if not output_path:
            output_path = output_dir / f"{subject.slug}.{fmt}"
        else:
            output_path = Path(output_path)

        # Get questions
        queryset = Question.objects.filter(subject=subject)
        if not options["include_inactive"]:
            queryset = queryset.filter(is_active=True)

        questions = queryset.order_by("difficulty", "created_at")

        # Skip subjects with no questions
        if questions.count() == 0:
            self.stdout.write(f"Skipping {subject.name} (no questions)")
            return

        if fmt == "json":
            self._export_json(subject, questions, output_path)
        else:
            self._export_sql(subject, questions, output_path)

        self.stdout.write(
            f"Exported {questions.count()} questions: {subject.name} -> {output_path}"
        )

    def _export_json(self, subject, questions, output_path):
        """Export questions to JSON format."""
        data = {
            "metadata": {
                "subject_slug": subject.slug,
                "subject_name": subject.name,
                "exported_at": datetime.now().isoformat(),
                "question_count": questions.count(),
                "format_version": "1.0",
            },
            "questions": [],
        }

        for q in questions:
            data["questions"].append({
                "question_text": q.question_text,
                "question_type": q.question_type,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "difficulty": q.difficulty,
                "tags": q.tags,
                "source": q.source,
                "is_active": q.is_active,
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _export_sql(self, subject, questions, output_path):
        """Export questions to SQL INSERT statements."""
        lines = [
            f"-- Questions export for: {subject.name}",
            f"-- Exported at: {datetime.now().isoformat()}",
            f"-- Question count: {questions.count()}",
            "",
            "-- Note: Run this after ensuring the subject exists",
            f"-- Subject slug: {subject.slug}",
            "",
        ]

        for q in questions:
            # Escape single quotes for SQL
            question_text = q.question_text.replace("'", "''")
            correct_answer = q.correct_answer.replace("'", "''")
            explanation = q.explanation.replace("'", "''") if q.explanation else ""

            options_json = json.dumps(q.options).replace("'", "''")
            tags_json = json.dumps(q.tags).replace("'", "''")

            lines.append(f"""
INSERT INTO questions_question (
    subject_id, question_text, question_type, options, correct_answer,
    explanation, difficulty, tags, source, is_active, created_at, updated_at
)
SELECT
    s.id,
    '{question_text}',
    '{q.question_type}',
    '{options_json}',
    '{correct_answer}',
    '{explanation}',
    '{q.difficulty}',
    '{tags_json}',
    '{q.source}',
    {str(q.is_active).upper()},
    NOW(),
    NOW()
FROM subjects_subject s
WHERE s.slug = '{subject.slug}'
ON CONFLICT DO NOTHING;
""")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
