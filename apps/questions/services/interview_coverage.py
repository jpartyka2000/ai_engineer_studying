"""Service for analyzing question coverage and generating interview-focused questions."""

import hashlib
import logging

from pydantic import BaseModel, Field

from apps.core.services.llm_service import LLMAPIError, get_llm_service
from apps.questions.models import Question
from apps.subjects.models import Subject

from .question_generator import GeneratedQuestion, GeneratedQuestionSet

logger = logging.getLogger(__name__)


class CoverageAnalysis(BaseModel):
    """Analysis of current question coverage for a subject."""

    covered_topics: list[str] = Field(
        description="Topics that are well-covered by existing questions"
    )
    partially_covered_topics: list[str] = Field(
        description="Topics that have some coverage but need more"
    )
    missing_topics: list[str] = Field(
        description="Important interview topics with no coverage"
    )
    coverage_summary: str = Field(
        description="Brief summary of the coverage analysis"
    )


class InterviewTopics(BaseModel):
    """Important interview topics for a subject."""

    essential_topics: list[str] = Field(
        description="Must-know topics for any interview"
    )
    common_topics: list[str] = Field(
        description="Frequently asked topics in interviews"
    )
    advanced_topics: list[str] = Field(
        description="Topics for senior/advanced positions"
    )
    total_estimated_questions: int = Field(
        description="Estimated number of questions needed for full coverage"
    )


class InterviewCoverageService:
    """
    Service for analyzing question coverage and generating interview-focused questions.

    This service:
    1. Analyzes existing questions to identify covered topics
    2. Identifies important interview topics that should be covered
    3. Generates questions to fill coverage gaps
    """

    ANALYSIS_SYSTEM_PROMPT = """You are an expert technical interviewer and curriculum designer.
Your task is to analyze question coverage and identify gaps in interview preparation materials.

Be thorough and specific. Consider what topics are most commonly asked in technical interviews
for the given subject area. Think about both fundamental concepts and practical applications.

You must respond with valid JSON only."""

    GENERATION_SYSTEM_PROMPT = """You are an expert exam question writer specializing in technical interviews.
Your task is to create high-quality interview questions that:
- Test real understanding, not just memorization
- Cover practical scenarios interviewers commonly ask about
- Range from basic concepts to advanced applications
- Include code examples where appropriate

For multiple choice questions, provide exactly 4 plausible options.
Make explanations educational - they should help the learner understand why.

You must respond with valid JSON only."""

    def __init__(self, provider: str | None = None) -> None:
        """Initialize the interview coverage service."""
        self.llm = get_llm_service(provider)

    def get_existing_coverage(self, subject: Subject) -> dict:
        """
        Analyze existing questions to understand current coverage.

        Returns a summary of topics covered by existing questions.
        """
        questions = Question.objects.filter(
            subject=subject,
            is_active=True,
        ).values_list("question_text", "tags", "difficulty")

        if not questions:
            return {
                "total_questions": 0,
                "questions_by_difficulty": {},
                "all_tags": [],
                "sample_questions": [],
            }

        # Aggregate data
        tags_set = set()
        difficulty_counts = {"beginner": 0, "intermediate": 0, "advanced": 0}
        sample_texts = []

        for q_text, tags, difficulty in questions:
            if tags:
                tags_set.update(tags)
            if difficulty in difficulty_counts:
                difficulty_counts[difficulty] += 1
            if len(sample_texts) < 20:  # Sample up to 20 questions
                sample_texts.append(q_text[:200])

        return {
            "total_questions": len(questions),
            "questions_by_difficulty": difficulty_counts,
            "all_tags": sorted(tags_set),
            "sample_questions": sample_texts,
        }

    def analyze_coverage(self, subject: Subject) -> CoverageAnalysis:
        """
        Use the LLM to analyze current coverage and identify gaps.

        Args:
            subject: The subject to analyze.

        Returns:
            CoverageAnalysis with covered, partially covered, and missing topics.
        """
        existing = self.get_existing_coverage(subject)

        prompt = f"""Analyze the question coverage for "{subject.name}" interview preparation.

Current State:
- Total questions: {existing['total_questions']}
- Questions by difficulty: {existing['questions_by_difficulty']}
- Topics covered (from tags): {', '.join(existing['all_tags']) or 'None'}

Sample existing questions:
{chr(10).join(f'- {q}' for q in existing['sample_questions'][:10]) or 'No questions yet'}

Based on your knowledge of what's commonly asked in technical interviews for {subject.name}:

1. Identify which important interview topics ARE well-covered
2. Identify topics that have SOME coverage but need more questions
3. Identify important interview topics that are MISSING entirely

Consider:
- Core concepts and fundamentals
- Common interview scenarios and problems
- Best practices and anti-patterns
- Practical applications
- Edge cases and gotchas interviewers love to ask about

Respond with JSON containing:
- covered_topics: Array of well-covered topics
- partially_covered_topics: Array of topics needing more questions
- missing_topics: Array of important topics with no coverage
- coverage_summary: Brief assessment of the current state"""

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message=self.ANALYSIS_SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.3,
            )
            return CoverageAnalysis.model_validate(response)

        except Exception as e:
            logger.exception("Failed to analyze coverage: %s", str(e))
            raise LLMAPIError(f"Coverage analysis failed: {e}") from e

    def get_interview_topics(self, subject: Subject) -> InterviewTopics:
        """
        Get the full list of important interview topics for a subject.

        Args:
            subject: The subject to get topics for.

        Returns:
            InterviewTopics with essential, common, and advanced topics.
        """
        prompt = f"""List all the important interview topics for "{subject.name}".

Consider what interviewers commonly ask about in technical interviews.
Be comprehensive - include everything a candidate should know.

Categorize topics by importance:
1. Essential topics: Must-know for ANY {subject.name} interview
2. Common topics: Frequently asked, expected for mid-level positions
3. Advanced topics: For senior positions or deep-dive interviews

Also estimate the total number of questions needed to adequately cover all these topics
(assume 2-4 questions per topic for good coverage).

Respond with JSON containing:
- essential_topics: Array of must-know topics
- common_topics: Array of frequently asked topics
- advanced_topics: Array of senior-level topics
- total_estimated_questions: Integer estimate"""

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message=self.ANALYSIS_SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.3,
            )
            return InterviewTopics.model_validate(response)

        except Exception as e:
            logger.exception("Failed to get interview topics: %s", str(e))
            raise LLMAPIError(f"Failed to get interview topics: {e}") from e

    def generate_gap_filling_questions(
        self,
        subject: Subject,
        num_questions: int | None = None,
        fill_until_complete: bool = False,
        difficulty: str | None = None,
    ) -> list[Question]:
        """
        Generate questions to fill coverage gaps.

        Args:
            subject: The subject to generate questions for.
            num_questions: Specific number of questions to generate.
                          If None and fill_until_complete is False, generates 10.
            fill_until_complete: If True, generates questions until all important
                                interview topics are covered (ignores num_questions).
            difficulty: Optional difficulty filter for generated questions.

        Returns:
            List of saved Question instances.
        """
        # First, analyze current coverage
        coverage = self.analyze_coverage(subject)

        logger.info(
            "Coverage analysis for %s: %d covered, %d partial, %d missing",
            subject.name,
            len(coverage.covered_topics),
            len(coverage.partially_covered_topics),
            len(coverage.missing_topics),
        )

        if fill_until_complete:
            return self._generate_until_complete(subject, coverage, difficulty)
        else:
            target_count = num_questions or 10
            return self._generate_n_questions(
                subject, coverage, target_count, difficulty
            )

    def _generate_n_questions(
        self,
        subject: Subject,
        coverage: CoverageAnalysis,
        num_questions: int,
        difficulty: str | None,
    ) -> list[Question]:
        """Generate a specific number of gap-filling questions."""
        # Prioritize missing topics, then partially covered
        priority_topics = coverage.missing_topics + coverage.partially_covered_topics

        if not priority_topics:
            logger.info("No coverage gaps found for %s", subject.name)
            # Generate general interview questions anyway
            priority_topics = ["general interview concepts"]

        difficulty_instruction = (
            f"All questions should be at '{difficulty}' difficulty level."
            if difficulty
            else "Vary difficulty levels (beginner, intermediate, advanced) appropriately."
        )

        prompt = f"""Generate {num_questions} interview questions for "{subject.name}".

Focus on these topics that need more coverage:
{chr(10).join(f'- {topic}' for topic in priority_topics[:15])}

Requirements:
- {difficulty_instruction}
- Questions should be what interviewers actually ask
- Include mix of conceptual and practical questions
- For multiple choice, provide exactly 4 options (A, B, C, D)
- Include clear explanations that teach the concept

Respond with JSON containing a "questions" array. Each question needs:
- question_text: The question (may include code blocks)
- question_type: "mc" or "free"
- options: Array of 4 strings for MC (empty array for free text)
- correct_answer: Letter for MC, full answer for free text
- explanation: Educational explanation of the answer
- difficulty: "beginner", "intermediate", or "advanced"
- tags: Array of relevant topic tags"""

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message=self.GENERATION_SYSTEM_PROMPT,
                max_tokens=8192,
                temperature=0.7,
            )

            question_set = GeneratedQuestionSet.model_validate(response)
            return self._save_questions(question_set.questions, subject)

        except Exception as e:
            logger.exception("Failed to generate questions: %s", str(e))
            raise LLMAPIError(f"Question generation failed: {e}") from e

    def _generate_until_complete(
        self,
        subject: Subject,
        coverage: CoverageAnalysis,
        difficulty: str | None,
    ) -> list[Question]:
        """Generate questions until all interview topics are adequately covered."""
        all_saved = []
        max_iterations = 10  # Safety limit
        questions_per_batch = 10

        for iteration in range(max_iterations):
            # Re-analyze coverage after each batch
            if iteration > 0:
                coverage = self.analyze_coverage(subject)

            # Check if we're done
            if not coverage.missing_topics and not coverage.partially_covered_topics:
                logger.info(
                    "Full coverage achieved for %s after %d iterations",
                    subject.name,
                    iteration,
                )
                break

            # Generate batch targeting remaining gaps
            topics_to_cover = (
                coverage.missing_topics[:5] + coverage.partially_covered_topics[:5]
            )

            if not topics_to_cover:
                break

            logger.info(
                "Iteration %d: Generating questions for %d topics",
                iteration + 1,
                len(topics_to_cover),
            )

            difficulty_instruction = (
                f"All questions should be at '{difficulty}' difficulty level."
                if difficulty
                else "Vary difficulty levels appropriately."
            )

            prompt = f"""Generate {questions_per_batch} interview questions for "{subject.name}".

These specific topics need coverage:
{chr(10).join(f'- {topic}' for topic in topics_to_cover)}

Requirements:
- {difficulty_instruction}
- Cover EACH of the listed topics with at least 1-2 questions
- Questions should test real interview scenarios
- Include mix of multiple choice and free text
- For MC, provide exactly 4 options (A, B, C, D)

Respond with JSON containing a "questions" array with:
question_text, question_type, options, correct_answer, explanation, difficulty, tags"""

            try:
                response = self.llm.generate_json_completion(
                    prompt=prompt,
                    system_message=self.GENERATION_SYSTEM_PROMPT,
                    max_tokens=8192,
                    temperature=0.7,
                )

                question_set = GeneratedQuestionSet.model_validate(response)
                saved = self._save_questions(question_set.questions, subject)
                all_saved.extend(saved)

                logger.info(
                    "Iteration %d: Saved %d questions (total: %d)",
                    iteration + 1,
                    len(saved),
                    len(all_saved),
                )

            except Exception as e:
                logger.exception("Failed in iteration %d: %s", iteration + 1, str(e))
                break

        return all_saved

    def _save_questions(
        self,
        questions: list[GeneratedQuestion],
        subject: Subject,
    ) -> list[Question]:
        """Save generated questions to the database."""
        saved = []

        for gen_q in questions:
            # Generate hash for deduplication
            content = f"{subject.id}:{gen_q.question_text}:{gen_q.correct_answer}"
            source_hash = hashlib.sha256(content.encode()).hexdigest()

            # Check for duplicates
            if Question.objects.filter(source_hash=source_hash).exists():
                logger.debug("Skipping duplicate: %s...", gen_q.question_text[:50])
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
                source=Question.Source.CLAUDE_API,
                source_hash=source_hash,
            )
            saved.append(question)

        return saved


# Singleton
_coverage_service: InterviewCoverageService | None = None


def get_interview_coverage_service(
    provider: str | None = None,
) -> InterviewCoverageService:
    """Get the singleton interview coverage service instance."""
    global _coverage_service
    if _coverage_service is None:
        _coverage_service = InterviewCoverageService(provider)
    return _coverage_service
