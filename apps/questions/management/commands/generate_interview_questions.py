"""Management command for generating interview-focused questions."""

from django.core.management.base import BaseCommand, CommandError

from apps.questions.services.interview_coverage import get_interview_coverage_service
from apps.subjects.models import Subject


class Command(BaseCommand):
    """Generate interview questions for a subject, filling coverage gaps."""

    help = (
        "Generate interview-focused questions for a subject. "
        "Analyzes existing questions, identifies gaps, and generates new questions "
        "to cover important interview topics."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "subject_slug",
            type=str,
            help="The slug of the subject to generate questions for",
        )
        parser.add_argument(
            "--num",
            "-n",
            type=int,
            default=None,
            help="Number of questions to generate (default: 10, or use --complete)",
        )
        parser.add_argument(
            "--complete",
            "-c",
            action="store_true",
            help="Generate questions until all important interview topics are covered",
        )
        parser.add_argument(
            "--difficulty",
            "-d",
            choices=["beginner", "intermediate", "advanced"],
            default=None,
            help="Generate questions at a specific difficulty level",
        )
        parser.add_argument(
            "--analyze-only",
            "-a",
            action="store_true",
            help="Only analyze coverage, don't generate questions",
        )
        parser.add_argument(
            "--show-topics",
            "-t",
            action="store_true",
            help="Show all important interview topics for the subject",
        )
        parser.add_argument(
            "--provider",
            "-p",
            choices=["claude", "openai"],
            default=None,
            help="LLM provider to use (default: claude)",
        )
        parser.add_argument(
            "--fix-difficulty",
            "-f",
            action="store_true",
            help="Find and fix questions with invalid difficulty values",
        )
        parser.add_argument(
            "--role",
            "-r",
            type=str,
            default="AI/ML engineer",
            help="Target role for interview coverage (default: 'AI/ML engineer')",
        )
        parser.add_argument(
            "--subtopic",
            "-s",
            type=str,
            default=None,
            help="Generate questions for a specific subtopic only",
        )

    def handle(self, *args, **options):
        subject_slug = options["subject_slug"]
        provider = options["provider"]
        role = options["role"]

        try:
            subject = Subject.objects.get(slug=subject_slug, is_active=True)
        except Subject.DoesNotExist:
            raise CommandError(f"Subject '{subject_slug}' not found or not active")

        service = get_interview_coverage_service(provider)

        self.stdout.write(f"Target role: {role}")
        if provider:
            self.stdout.write(f"Using LLM provider: {provider}")

        # Fix difficulty values if requested
        if options["fix_difficulty"]:
            self.stdout.write(
                self.style.MIGRATE_HEADING(f"\nFixing difficulty values: {subject.name}")
            )
            try:
                updated = service.fix_question_difficulties(subject)
                if updated:
                    self.stdout.write(
                        self.style.SUCCESS(f"\nUpdated {len(updated)} questions:")
                    )
                    for q in updated:
                        self.stdout.write(
                            f"  [{q.difficulty}] {q.question_text[:60]}..."
                        )
                else:
                    self.stdout.write(
                        self.style.SUCCESS("\nNo questions needed difficulty fixes.")
                    )
            except Exception as e:
                raise CommandError(f"Failed to fix difficulty values: {e}")
            return

        # Show interview topics if requested
        if options["show_topics"]:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\nInterview Topics: {subject.name}"))
            try:
                topics = service.get_interview_topics(subject, role=role)
                self.stdout.write(
                    f"\nEstimated questions needed: {topics.total_estimated_questions}"
                )
                self.stdout.write(self.style.SUCCESS("\nEssential Topics:"))
                for topic in topics.essential_topics:
                    self.stdout.write(f"  - {topic}")
                self.stdout.write(self.style.WARNING("\nCommon Topics:"))
                for topic in topics.common_topics:
                    self.stdout.write(f"  - {topic}")
                self.stdout.write(self.style.NOTICE("\nAdvanced Topics:"))
                for topic in topics.advanced_topics:
                    self.stdout.write(f"  - {topic}")
            except Exception as e:
                raise CommandError(f"Failed to get interview topics: {e}")
            return

        # Generate questions for a specific subtopic
        if options["subtopic"]:
            subtopic = options["subtopic"]
            num = options["num"] or 10
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"\nGenerating {num} questions for subtopic: {subtopic}"
                )
            )
            try:
                saved = service.generate_subtopic_questions(
                    subject=subject,
                    subtopic=subtopic,
                    num_questions=num,
                    difficulty=options["difficulty"],
                    role=role,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"\nGenerated and saved {len(saved)} questions:")
                )
                for q in saved:
                    self.stdout.write(
                        f"  [{q.difficulty}] {q.question_text[:60]}..."
                    )
            except Exception as e:
                raise CommandError(f"Failed to generate subtopic questions: {e}")
            return

        # Analyze coverage
        self.stdout.write(self.style.MIGRATE_HEADING(f"\nAnalyzing coverage: {subject.name}"))

        existing = service.get_existing_coverage(subject)
        self.stdout.write(f"Total existing questions: {existing['total_questions']}")
        self.stdout.write(
            f"By difficulty: {existing['questions_by_difficulty']}"
        )
        if existing["all_tags"]:
            self.stdout.write(f"Topics covered: {', '.join(existing['all_tags'][:20])}")

        try:
            coverage = service.analyze_coverage(subject, role=role)
        except Exception as e:
            raise CommandError(f"Failed to analyze coverage: {e}")

        self.stdout.write(f"\n{coverage.coverage_summary}")

        if coverage.covered_topics:
            self.stdout.write(
                self.style.SUCCESS(f"\nWell covered ({len(coverage.covered_topics)}):")
            )
            self.stdout.write(f"  {', '.join(coverage.get_covered_topic_names())}")

        if coverage.partially_covered_topics:
            self.stdout.write(
                self.style.WARNING(
                    f"\nNeeds more coverage ({len(coverage.partially_covered_topics)}):"
                )
            )
            self.stdout.write(f"  {', '.join(coverage.get_partial_topic_names())}")

        if coverage.missing_topics:
            self.stdout.write(
                self.style.ERROR(f"\nMissing ({len(coverage.missing_topics)}):")
            )
            self.stdout.write(f"  {', '.join(coverage.get_missing_topic_names())}")

        # Display sufficiency status (informational only)
        if coverage.is_sufficient_for_role:
            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Coverage is SUFFICIENT for {role} interviews")
            )
        else:
            self.stdout.write(
                self.style.WARNING(f"\n✗ Coverage is NOT YET sufficient for {role} interviews")
            )

        # Stop here if analyze-only
        if options["analyze_only"]:
            return

        # Check if there are any topics to generate questions for
        if not coverage.missing_topics and not coverage.partially_covered_topics:
            self.stdout.write(
                self.style.SUCCESS("\nNo gaps found - all topics are well covered!")
            )
            return

        # Generate questions
        self.stdout.write(self.style.MIGRATE_HEADING("\nGenerating questions..."))

        try:
            if options["complete"]:
                self.stdout.write("Mode: Generate until full coverage")
                saved = service.generate_gap_filling_questions(
                    subject=subject,
                    fill_until_complete=True,
                    difficulty=options["difficulty"],
                    role=role,
                )
            else:
                num = options["num"] or 10
                self.stdout.write(f"Mode: Generate {num} questions")
                saved = service.generate_gap_filling_questions(
                    subject=subject,
                    num_questions=num,
                    difficulty=options["difficulty"],
                    role=role,
                )

            self.stdout.write(
                self.style.SUCCESS(f"\nGenerated and saved {len(saved)} questions:")
            )
            for q in saved:
                self.stdout.write(
                    f"  [{q.difficulty}] {q.question_text[:60]}..."
                )

        except Exception as e:
            raise CommandError(f"Failed to generate questions: {e}")
