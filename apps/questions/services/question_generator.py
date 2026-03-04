"""Service for generating exam questions using Claude API."""

import hashlib
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from apps.core.services.claude_service import ClaudeAPIError, get_claude_service
from apps.questions.models import Question
from apps.subjects.models import Subject

logger = logging.getLogger(__name__)


class GeneratedQuestion(BaseModel):
    """Pydantic model for a generated question from Claude."""

    question_text: str = Field(description="The question text")
    question_type: str = Field(
        description="Either 'mc' for multiple choice or 'free' for free text"
    )
    options: list[str] = Field(
        default_factory=list, description="Answer options for MC questions"
    )
    correct_answer: str = Field(
        description="The correct answer (letter for MC, text for free)"
    )
    explanation: str = Field(description="Explanation of why the answer is correct")
    difficulty: str = Field(
        default="intermediate", description="beginner, intermediate, or advanced"
    )
    tags: list[str] = Field(
        default_factory=list, description="Topic tags for the question"
    )


class GeneratedQuestionSet(BaseModel):
    """Pydantic model for a set of generated questions."""

    questions: list[GeneratedQuestion]


class QuestionGeneratorService:
    """
    Service for generating exam questions from source material or topics.

    Uses the Claude API to convert explanatory content into structured
    exam questions (multiple choice and free text).
    """

    SYSTEM_PROMPT = """You are an expert exam question writer for technical subjects.
Your task is to create high-quality exam questions that test understanding, not just memorization.

Guidelines:
- Create questions that test real comprehension of concepts
- For multiple choice (mc): provide exactly 4 options (A, B, C, D)
- Make wrong answers plausible but clearly incorrect to someone who understands the material
- Include code snippets where appropriate (use markdown code blocks)
- Explanations should teach, not just state the answer
- Vary difficulty levels appropriately
- Tags should be specific topics covered by the question

You must respond with valid JSON only."""

    def __init__(self) -> None:
        """Initialize the question generator service."""
        self.claude = get_claude_service()

    def generate_from_content(
        self,
        content: str,
        subject: Subject,
        topic: str,
        num_questions: int = 3,
        difficulty: str | None = None,
        question_types: list[str] | None = None,
    ) -> list[GeneratedQuestion]:
        """
        Generate exam questions from source content using Claude.

        Args:
            content: The source material to generate questions from.
            subject: The subject this content belongs to.
            topic: The specific topic name (e.g., from filename).
            num_questions: Number of questions to generate.
            difficulty: Target difficulty level.
            question_types: List of question types to generate ['mc', 'free'].
                          Defaults to both if not specified.

        Returns:
            List of generated questions.

        Raises:
            ClaudeAPIError: If question generation fails.
        """
        if question_types is None:
            question_types = ["mc", "free"]

        # Build difficulty instruction
        if difficulty:
            difficulty_instruction = f"- Generate questions at the '{difficulty}' difficulty level"
            difficulty_constraint = f'  "difficulty": "{difficulty}"'
        else:
            difficulty_instruction = (
                "- Assign appropriate difficulty level (beginner/intermediate/advanced) to each question based on:\n"
                "  * Beginner: Basic concepts, definitions, simple recall\n"
                "  * Intermediate: Application of concepts, problem-solving, understanding relationships\n"
                "  * Advanced: Complex scenarios, edge cases, optimization, deep understanding"
            )
            difficulty_constraint = '  "difficulty": "intermediate" (or "beginner" or "advanced" based on complexity)'

        prompt = f"""Based on the following content about "{topic}" in the subject area of "{subject.name}",
generate {num_questions} exam questions.

Requirements:
{difficulty_instruction}
- Include a mix of question types: {", ".join(question_types)}
- For multiple choice questions, provide exactly 4 options labeled A, B, C, D
- The correct_answer for MC questions should be just the letter (e.g., "A")
- Include clear explanations for each answer
- Add relevant tags for each question

Source Content:
---
{content}
---

Respond with a JSON object containing a "questions" array. Each question should have:
- question_text: The question (may include code blocks)
- question_type: "mc" or "free"
- options: Array of 4 strings for MC (empty for free text)
- correct_answer: Letter for MC, full answer for free text
- explanation: Why this is the correct answer
- difficulty: One of "beginner", "intermediate", or "advanced"
- tags: Array of relevant topic tags

Example response format:
{{
  "questions": [
    {{
      "question_text": "What is the default value of num_leaves in LightGBM?",
      "question_type": "mc",
      "options": ["21", "31", "41", "51"],
      "correct_answer": "B",
      "explanation": "The default value for num_leaves in LightGBM is 31...",
{difficulty_constraint},
      "tags": ["lightgbm", "hyperparameters", "num_leaves"]
    }}
  ]
}}"""

        try:
            response = self.claude.generate_json_completion(
                prompt=prompt,
                system_message=self.SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.7,
            )

            # Validate response
            question_set = GeneratedQuestionSet.model_validate(response)
            return question_set.questions

        except ClaudeAPIError:
            raise
        except Exception as e:
            logger.exception("Failed to generate questions: %s", str(e))
            raise ClaudeAPIError(f"Question generation failed: {e}") from e

    def generate_from_topic(
        self,
        subject: Subject,
        topic: str,
        num_questions: int = 5,
        difficulty: str | None = None,
    ) -> list[GeneratedQuestion]:
        """
        Generate exam questions directly from a topic name using Claude's knowledge.

        Args:
            subject: The subject area.
            topic: The topic to generate questions about.
            num_questions: Number of questions to generate.
            difficulty: Target difficulty level.

        Returns:
            List of generated questions.
        """
        # Build difficulty instruction
        if difficulty:
            difficulty_instruction = f"- Questions should be at the '{difficulty}' difficulty level"
        else:
            difficulty_instruction = (
                "- Assign appropriate difficulty level (beginner/intermediate/advanced) to each question based on:\n"
                "  * Beginner: Basic concepts, definitions, simple recall\n"
                "  * Intermediate: Application of concepts, problem-solving, understanding relationships\n"
                "  * Advanced: Complex scenarios, edge cases, optimization, deep understanding"
            )

        prompt = f"""Generate {num_questions} exam questions about "{topic}"
in the subject area of "{subject.name}".

Requirements:
{difficulty_instruction}
- Include a mix of multiple choice and free text questions
- For multiple choice, provide exactly 4 options (A, B, C, D)
- Test real understanding, not just memorization
- Include practical/applied questions where appropriate

Respond with a JSON object containing a "questions" array with the following fields
for each question:
- question_text, question_type ("mc" or "free"), options, correct_answer,
  explanation, difficulty, tags"""

        try:
            response = self.claude.generate_json_completion(
                prompt=prompt,
                system_message=self.SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.7,
            )

            question_set = GeneratedQuestionSet.model_validate(response)
            return question_set.questions

        except Exception as e:
            logger.exception("Failed to generate questions from topic: %s", str(e))
            raise ClaudeAPIError(f"Question generation failed: {e}") from e

    def save_questions(
        self,
        questions: list[GeneratedQuestion],
        subject: Subject,
        source: str = Question.Source.CLAUDE_API,
        source_file: str = "",
    ) -> list[Question]:
        """
        Save generated questions to the database.

        Args:
            questions: List of generated questions to save.
            subject: The subject these questions belong to.
            source: The source of these questions.
            source_file: Path to source file (for llm_studying questions).

        Returns:
            List of saved Question model instances.
        """
        saved_questions = []

        for gen_q in questions:
            # Generate hash for deduplication
            content = f"{subject.id}:{gen_q.question_text}:{gen_q.correct_answer}"
            source_hash = hashlib.sha256(content.encode()).hexdigest()

            # Check if question already exists
            if Question.objects.filter(source_hash=source_hash).exists():
                logger.info(
                    "Question already exists, skipping: %s...", gen_q.question_text[:50]
                )
                continue

            question = Question.objects.create(
                subject=subject,
                question_text=gen_q.question_text,
                question_type=gen_q.question_type,
                options=gen_q.options,
                correct_answer=gen_q.correct_answer,
                explanation=gen_q.explanation,
                difficulty=gen_q.difficulty,
                tags=gen_q.tags,
                source=source,
                source_file=source_file,
                source_hash=source_hash,
            )
            saved_questions.append(question)
            logger.info("Saved question: %s", question)

        return saved_questions

    def import_from_file(
        self,
        file_path: Path,
        subject: Subject,
        num_questions: int = 3,
        difficulty: str | None = None,
    ) -> list[Question]:
        """
        Import questions from an llm_studying file.

        Reads the file content, generates questions using Claude,
        and saves them to the database.

        Args:
            file_path: Path to the source file.
            subject: The subject this file belongs to.
            num_questions: Number of questions to generate per file.
            difficulty: Target difficulty level.

        Returns:
            List of saved Question instances.
        """
        # Extract topic from filename
        topic = file_path.stem.replace("_", " ").replace("about ", "")

        # Read file content
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("Failed to read file %s: %s", file_path, e)
            return []

        if not content.strip():
            logger.warning("Empty file: %s", file_path)
            return []

        # Generate questions from content
        try:
            generated = self.generate_from_content(
                content=content,
                subject=subject,
                topic=topic,
                num_questions=num_questions,
                difficulty=difficulty,
            )
        except ClaudeAPIError as e:
            logger.error("Failed to generate questions from %s: %s", file_path, e)
            return []

        # Save questions
        return self.save_questions(
            questions=generated,
            subject=subject,
            source=Question.Source.LLM_STUDYING,
            source_file=str(file_path),
        )


# Singleton instance
_question_generator: QuestionGeneratorService | None = None


def get_question_generator() -> QuestionGeneratorService:
    """Get the singleton question generator instance."""
    global _question_generator
    if _question_generator is None:
        _question_generator = QuestionGeneratorService()
    return _question_generator
