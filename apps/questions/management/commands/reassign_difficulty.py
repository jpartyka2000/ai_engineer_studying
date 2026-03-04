"""Management command to re-assign difficulty levels to existing questions."""

import time

from django.core.management.base import BaseCommand
from pydantic import BaseModel, Field

from apps.core.services.claude_service import ClaudeAPIError, get_claude_service
from apps.questions.models import Question
from apps.subjects.models import Subject


class DifficultyAssignment(BaseModel):
    """Pydantic model for difficulty assignment response."""

    difficulty: str = Field(
        description="The assigned difficulty level: beginner, intermediate, or advanced"
    )
    reasoning: str = Field(description="Brief explanation of the difficulty assignment")


class Command(BaseCommand):
    """Re-assign difficulty levels to existing questions using Claude."""

    help = "Re-assign difficulty levels to existing questions based on their complexity"

    SYSTEM_PROMPT = """You are an expert at evaluating the difficulty of exam questions.
Your task is to assign an appropriate difficulty level to each question based on its complexity.

Difficulty Levels:
- beginner: Basic concepts, definitions, simple recall, straightforward application
- intermediate: Application of concepts, problem-solving, understanding relationships, multiple steps
- advanced: Complex scenarios, edge cases, optimization, deep understanding, synthesis of multiple concepts

Consider:
- The cognitive load required
- Prior knowledge needed
- Number of concepts involved
- Complexity of reasoning required

You must respond with valid JSON only."""

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--subject",
            type=str,
            help="Only process questions for a specific subject (slug)",
        )
        parser.add_argument(
            "--current-difficulty",
            type=str,
            choices=["beginner", "intermediate", "advanced"],
            help="Only process questions with this current difficulty level",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without actually updating",
        )
        parser.add_argument(
            "--max-questions",
            type=int,
            help="Maximum number of questions to process",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.5,
            help="Delay in seconds between API calls to avoid rate limiting",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        # Build query
        queryset = Question.objects.all().select_related("subject")

        if options["subject"]:
            subject = Subject.objects.filter(slug=options["subject"]).first()
            if not subject:
                self.stdout.write(
                    self.style.ERROR(f"Subject not found: {options['subject']}")
                )
                return
            queryset = queryset.filter(subject=subject)
            self.stdout.write(f"Filtering by subject: {subject.name}")

        if options["current_difficulty"]:
            queryset = queryset.filter(difficulty=options["current_difficulty"])
            self.stdout.write(
                f"Filtering by current difficulty: {options['current_difficulty']}"
            )

        if options["max_questions"]:
            queryset = queryset[: options["max_questions"]]

        total_questions = queryset.count()
        self.stdout.write(f"\nFound {total_questions} questions to process")

        if total_questions == 0:
            self.stdout.write(self.style.WARNING("No questions found"))
            return

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN - No changes will be made\n")
            )

        # Process questions
        claude_service = get_claude_service()
        updated_count = 0
        unchanged_count = 0
        error_count = 0

        for i, question in enumerate(queryset, 1):
            self.stdout.write(
                f"\n[{i}/{total_questions}] Processing question {question.id}..."
            )
            self.stdout.write(f"  Subject: {question.subject.name}")
            self.stdout.write(f"  Current difficulty: {question.difficulty}")
            self.stdout.write(f"  Question: {question.question_text[:80]}...")

            try:
                # Build prompt for Claude
                prompt = self.build_evaluation_prompt(question)

                # Get difficulty assignment from Claude
                response = claude_service.generate_json_completion(
                    prompt=prompt,
                    system_message=self.SYSTEM_PROMPT,
                    max_tokens=512,
                    temperature=0.3,  # Lower temperature for more consistent evaluation
                )

                # Validate response
                assignment = DifficultyAssignment.model_validate(response)
                new_difficulty = assignment.difficulty

                self.stdout.write(f"  New difficulty: {new_difficulty}")
                self.stdout.write(f"  Reasoning: {assignment.reasoning}")

                # Update question if changed
                if new_difficulty != question.difficulty:
                    if not options["dry_run"]:
                        question.difficulty = new_difficulty
                        question.save(update_fields=["difficulty"])
                        self.stdout.write(self.style.SUCCESS("  ✓ Updated difficulty"))
                    else:
                        self.stdout.write(
                            self.style.WARNING("  → Would update difficulty")
                        )
                    updated_count += 1
                else:
                    self.stdout.write("  No change needed")
                    unchanged_count += 1

            except ClaudeAPIError as e:
                self.stdout.write(self.style.ERROR(f"  ✗ API error: {e}"))
                error_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))
                error_count += 1

            # Delay to avoid rate limiting
            if options["delay"] > 0 and i < total_questions:
                time.sleep(options["delay"])

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("\nProcessing complete!"))
        self.stdout.write(f"  Total processed: {total_questions}")
        self.stdout.write(f"  Updated: {updated_count}")
        self.stdout.write(f"  Unchanged: {unchanged_count}")
        self.stdout.write(f"  Errors: {error_count}")

    def build_evaluation_prompt(self, question: Question) -> str:
        """Build prompt for Claude to evaluate question difficulty."""
        prompt_parts = [
            f"Subject Area: {question.subject.name}\n",
            f"Question Type: {'Multiple Choice' if question.question_type == 'mc' else 'Free Text'}\n",
            f"\nQuestion:\n{question.question_text}\n",
        ]

        if question.question_type == "mc" and question.options:
            prompt_parts.append("\nOptions:")
            for i, option in enumerate(question.options, 1):
                prompt_parts.append(f"  {chr(64 + i)}. {option}")
            prompt_parts.append(f"\nCorrect Answer: {question.correct_answer}\n")

        prompt_parts.append(
            "\nEvaluate the difficulty of this question and respond with JSON containing:\n"
            '- "difficulty": One of "beginner", "intermediate", or "advanced"\n'
            '- "reasoning": Brief explanation (1-2 sentences) of why you assigned this level\n'
            "\nExample response format:\n"
            '{\n  "difficulty": "intermediate",\n  '
            '"reasoning": "This question requires understanding of relationships '
            'between concepts and multi-step reasoning."\n}'
        )

        return "".join(prompt_parts)
