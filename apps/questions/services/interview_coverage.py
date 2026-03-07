"""Service for analyzing question coverage and generating interview-focused questions."""

import hashlib
import logging

from pydantic import BaseModel, Field, field_validator

from apps.core.services.llm_service import LLMAPIError, get_llm_service
from apps.questions.models import Question
from apps.subjects.models import Subject

from .question_generator import GeneratedQuestion, GeneratedQuestionSet

logger = logging.getLogger(__name__)


class TopicEntry(BaseModel):
    """A topic entry that can be a string or structured object."""

    topic: str
    description: str | None = None
    # Normalized to int or None (LLM may return various formats)
    suggested_additions: int | None = None

    @field_validator("suggested_additions", mode="before")
    @classmethod
    def normalize_suggested_additions(cls, v):
        """Normalize suggested_additions to int or None."""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, list):
            return len(v)  # Convert list to count
        # String or other type - ignore it
        return None

    @classmethod
    def from_input(cls, value: str | dict) -> "TopicEntry":
        """Create a TopicEntry from either a string or dict."""
        if isinstance(value, str):
            return cls(topic=value)
        # Handle various dict formats the LLM might return
        if isinstance(value, dict):
            # Extract just the topic name, ignore other fields that might cause issues
            topic = value.get("topic", str(value))
            description = value.get("description")
            suggested = value.get("suggested_additions")
            return cls(topic=topic, description=description, suggested_additions=suggested)
        return cls(topic=str(value))

    def __str__(self) -> str:
        return self.topic


def parse_topic_list(values: list[str | dict]) -> list[TopicEntry]:
    """Parse a list of topics that can be strings or dicts."""
    return [TopicEntry.from_input(v) for v in values]


class CoverageAnalysis(BaseModel):
    """Analysis of current question coverage for a subject."""

    covered_topics: list[str | TopicEntry] = Field(
        description="Topics that are well-covered by existing questions"
    )
    partially_covered_topics: list[str | TopicEntry] = Field(
        description="Topics that have some coverage but need more"
    )
    missing_topics: list[str | TopicEntry] = Field(
        description="Important interview topics with no coverage"
    )
    coverage_summary: str = Field(
        description="Brief summary of the coverage analysis"
    )
    is_sufficient_for_role: bool = Field(
        default=False,
        description="Whether the current coverage is sufficient for the target role",
    )

    @field_validator("is_sufficient_for_role", mode="before")
    @classmethod
    def normalize_is_sufficient(cls, v):
        """Handle various formats for is_sufficient_for_role."""
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "yes", "1", "sufficient", "complete")
        if isinstance(v, dict):
            # Handle {"value": true, "reason": "..."} format
            return bool(v.get("value", v.get("sufficient", False)))
        return bool(v)

    @field_validator("coverage_summary", mode="before")
    @classmethod
    def normalize_coverage_summary(cls, v):
        """Convert dict to string if LLM returns structured summary."""
        if v is None:
            return "No summary provided."
        if isinstance(v, dict):
            # Try to extract a meaningful string from the dict
            if "overall_assessment" in v:
                return str(v["overall_assessment"])
            if "summary" in v:
                return str(v["summary"])
            # Fallback: join all values
            return " ".join(str(val) for val in v.values())
        return str(v)

    def model_post_init(self, __context) -> None:
        """Convert all topics to TopicEntry objects after validation."""
        self.covered_topics = parse_topic_list(self.covered_topics)
        self.partially_covered_topics = parse_topic_list(self.partially_covered_topics)
        self.missing_topics = parse_topic_list(self.missing_topics)

    def get_covered_topic_names(self) -> list[str]:
        """Get just the topic names from covered topics."""
        return [str(t) for t in self.covered_topics]

    def get_missing_topic_names(self) -> list[str]:
        """Get just the topic names from missing topics."""
        return [str(t) for t in self.missing_topics]

    def get_partial_topic_names(self) -> list[str]:
        """Get just the topic names from partially covered topics."""
        return [str(t) for t in self.partially_covered_topics]


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

    def analyze_coverage(
        self, subject: Subject, role: str = "AI/ML engineer"
    ) -> CoverageAnalysis:
        """
        Use the LLM to analyze current coverage and identify gaps.

        Args:
            subject: The subject to analyze.
            role: Target role for interview coverage (e.g., "AI/ML engineer").

        Returns:
            CoverageAnalysis with covered, partially covered, and missing topics.
        """
        existing = self.get_existing_coverage(subject)

        prompt = f"""Analyze the question coverage for "{subject.name}" interview preparation.

IMPORTANT: This is for a {role} interview, NOT a {subject.name} specialist interview.
Focus ONLY on {subject.name} topics that are commonly asked in {role} interviews.
Do NOT include niche or specialist topics that wouldn't appear in a typical {role} interview.

Current State:
- Total questions: {existing['total_questions']}
- Questions by difficulty: {existing['questions_by_difficulty']}
- Topics covered (from tags): {', '.join(existing['all_tags']) or 'None'}

Sample existing questions:
{chr(10).join(f'- {q}' for q in existing['sample_questions'][:10]) or 'No questions yet'}

Based on what a {role} would REALISTICALLY be asked about {subject.name} in interviews:

1. Identify which important topics ARE well-covered
2. Identify topics that have SOME coverage but need more questions
3. Identify important topics that are MISSING entirely

ORDERING: List topics in order of importance/fundamentalness:
- Most fundamental/commonly-asked topics FIRST
- More niche/advanced topics LAST
This ensures the most critical gaps are filled first.

CRITICAL: Evaluate if the current coverage is SUFFICIENT for a {role} interview.
Coverage is SUFFICIENT when:
- All core {subject.name} concepts a {role} needs are covered
- There's good depth across beginner/intermediate/advanced levels
- The existing questions would prepare someone for 90%+ of {subject.name} questions in a {role} interview

Be realistic - a {role} doesn't need to know everything about {subject.name}.
If coverage is already strong for the target role, set is_sufficient_for_role to true.
Even if sufficient, still list any remaining gaps in order of importance.

Respond with JSON containing:
- covered_topics: Array of well-covered topics
- partially_covered_topics: Array of topics needing more questions, ordered by importance (most fundamental first)
- missing_topics: Array of missing topics, ordered by importance (most fundamental first)
- coverage_summary: Brief assessment of the current state
- is_sufficient_for_role: Boolean - true if coverage is sufficient for a {role} interview"""

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message=self.ANALYSIS_SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.3,
            )
            return CoverageAnalysis.model_validate(response)

        except Exception as e:
            logger.exception("Failed to analyze coverage: %s", str(e))
            raise LLMAPIError(f"Coverage analysis failed: {e}") from e

    def get_interview_topics(
        self, subject: Subject, role: str = "AI/ML engineer"
    ) -> InterviewTopics:
        """
        Get the full list of important interview topics for a subject.

        Args:
            subject: The subject to get topics for.
            role: Target role for interview coverage (e.g., "AI/ML engineer").

        Returns:
            InterviewTopics with essential, common, and advanced topics.
        """
        prompt = f"""List the important "{subject.name}" interview topics for a {role} position.

IMPORTANT: Focus on {subject.name} topics relevant to {role} interviews, NOT topics for
{subject.name} specialists. A {role} needs practical working knowledge, not deep expertise.

Categorize topics by importance for a {role}:
1. Essential topics: Must-know {subject.name} concepts for ANY {role} interview
2. Common topics: Frequently asked, expected for mid-level {role} positions
3. Advanced topics: For senior {role} positions or deep-dive interviews

Consider what {subject.name} knowledge helps a {role} in their daily work:
- Practical usage patterns
- Common workflows and integrations
- Troubleshooting skills
- Best practices relevant to {role} work

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
                max_tokens=4096,
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
        role: str = "AI/ML engineer",
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
            role: Target role for interview coverage (e.g., "AI/ML engineer").

        Returns:
            List of saved Question instances.
        """
        # First, analyze current coverage
        coverage = self.analyze_coverage(subject, role=role)

        logger.info(
            "Coverage analysis for %s: %d covered, %d partial, %d missing",
            subject.name,
            len(coverage.covered_topics),
            len(coverage.partially_covered_topics),
            len(coverage.missing_topics),
        )

        if fill_until_complete:
            return self._generate_until_complete(subject, coverage, difficulty, role)
        else:
            target_count = num_questions or 10
            return self._generate_n_questions(
                subject, coverage, target_count, difficulty, role
            )

    def _generate_n_questions(
        self,
        subject: Subject,
        coverage: CoverageAnalysis,
        num_questions: int,
        difficulty: str | None,
        role: str = "AI/ML engineer",
    ) -> list[Question]:
        """Generate a specific number of gap-filling questions."""
        # Prioritize missing topics, then partially covered (as string lists)
        priority_topics = (
            coverage.get_missing_topic_names() + coverage.get_partial_topic_names()
        )

        if not priority_topics:
            logger.info("No coverage gaps found for %s", subject.name)
            # Generate general interview questions anyway
            priority_topics = ["general interview concepts"]

        difficulty_instruction = (
            f"All questions should be at '{difficulty}' difficulty level."
            if difficulty
            else "Vary difficulty levels (beginner, intermediate, advanced) appropriately."
        )

        prompt = f"""Generate {num_questions} interview questions about "{subject.name}" for a {role} position.

IMPORTANT: These questions are for {role} interviews, NOT {subject.name} specialist interviews.
Focus on practical {subject.name} knowledge that a {role} would actually need.

Topics that need more coverage:
{chr(10).join(f'- {topic}' for topic in priority_topics[:15])}

Requirements:
- {difficulty_instruction}
- Questions should reflect what {role} candidates are actually asked
- Focus on practical scenarios a {role} would encounter
- For multiple choice, provide exactly 4 options (A, B, C, D)
- Include clear explanations that teach the concept

Respond with JSON containing a "questions" array. Each question needs:
- question_text: The question (may include code blocks)
- question_type: "mc" or "free"
- options: Array of 4 strings for MC (empty array for free text)
- correct_answer: Letter for MC, full answer for free text
- explanation: Educational explanation of the answer
- difficulty: MUST be one of "beginner", "intermediate", or "advanced"
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
        role: str = "AI/ML engineer",
    ) -> list[Question]:
        """Generate questions until all interview topics are adequately covered."""
        all_saved = []
        max_iterations = 10  # Safety limit
        questions_per_batch = 10

        for iteration in range(max_iterations):
            # Re-analyze coverage after each batch
            if iteration > 0:
                coverage = self.analyze_coverage(subject, role=role)

            # Log sufficiency status (informational only)
            if coverage.is_sufficient_for_role:
                logger.info(
                    "Coverage is sufficient for %s role, but continuing to fill gaps",
                    role,
                )

            # Check if we're done (no gaps)
            if not coverage.missing_topics and not coverage.partially_covered_topics:
                logger.info(
                    "Full coverage achieved for %s after %d iterations",
                    subject.name,
                    iteration,
                )
                break

            # Generate batch targeting remaining gaps (as string lists)
            missing = coverage.get_missing_topic_names()[:5]
            partial = coverage.get_partial_topic_names()[:5]
            topics_to_cover = missing + partial

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
                else "Vary difficulty levels (beginner, intermediate, advanced) appropriately."
            )

            prompt = f"""Generate {questions_per_batch} interview questions about "{subject.name}" for a {role} position.

IMPORTANT: These questions are for {role} interviews, NOT {subject.name} specialist interviews.
Focus on practical {subject.name} knowledge that a {role} would actually need.

These specific topics need coverage:
{chr(10).join(f'- {topic}' for topic in topics_to_cover)}

Requirements:
- {difficulty_instruction}
- Cover EACH of the listed topics with at least 1-2 questions
- Questions should reflect what {role} candidates are actually asked
- Focus on practical scenarios a {role} would encounter
- Include mix of multiple choice and free text
- For MC, provide exactly 4 options (A, B, C, D)

Respond with JSON containing a "questions" array. Each question needs:
- question_text: The question (may include code blocks)
- question_type: "mc" or "free"
- options: Array of 4 strings for MC (empty array for free text)
- correct_answer: Letter for MC, full answer for free text
- explanation: Educational explanation of the answer
- difficulty: MUST be one of "beginner", "intermediate", or "advanced"
- tags: Array of relevant topic tags"""

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

    def generate_subtopic_questions(
        self,
        subject: Subject,
        subtopic: str,
        num_questions: int = 10,
        difficulty: str | None = None,
        role: str = "AI/ML engineer",
    ) -> list[Question]:
        """
        Generate questions for a specific subtopic.

        Args:
            subject: The subject area.
            subtopic: The specific subtopic to generate questions for.
            num_questions: Number of questions to generate.
            difficulty: Optional difficulty filter.
            role: Target role for the questions.

        Returns:
            List of saved Question instances.
        """
        difficulty_instruction = (
            f"All questions should be at '{difficulty}' difficulty level."
            if difficulty
            else "Vary difficulty levels (beginner, intermediate, advanced) appropriately."
        )

        prompt = f"""Generate {num_questions} interview questions about "{subtopic}" within the context of "{subject.name}" for a {role} position.

IMPORTANT: Focus specifically on "{subtopic}" - do not generate questions about other topics.
These questions are for {role} interviews, so focus on practical knowledge.

Requirements:
- {difficulty_instruction}
- All questions must be specifically about "{subtopic}"
- Questions should reflect what {role} candidates are actually asked
- Focus on practical scenarios a {role} would encounter
- For multiple choice, provide exactly 4 options (A, B, C, D)
- Include clear explanations that teach the concept

Respond with JSON containing a "questions" array. Each question needs:
- question_text: The question (may include code blocks)
- question_type: "mc" or "free"
- options: Array of 4 strings for MC (empty array for free text)
- correct_answer: Letter for MC, full answer for free text
- explanation: Educational explanation of the answer
- difficulty: MUST be one of "beginner", "intermediate", or "advanced"
- tags: Array of relevant topic tags (must include "{subtopic}")"""

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
            logger.exception("Failed to generate subtopic questions: %s", str(e))
            raise LLMAPIError(f"Subtopic question generation failed: {e}") from e

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

    def fix_question_difficulties(
        self,
        subject: Subject,
        batch_size: int = 10,
    ) -> list[Question]:
        """
        Find questions with invalid difficulty and use LLM to assign correct values.

        Args:
            subject: The subject to fix questions for.
            batch_size: Number of questions to process per LLM call.

        Returns:
            List of updated Question instances.
        """
        valid_difficulties = {"beginner", "intermediate", "advanced"}

        # Find questions with invalid difficulty values
        questions_to_fix = list(
            Question.objects.filter(subject=subject, is_active=True).exclude(
                difficulty__in=valid_difficulties
            )
        )

        if not questions_to_fix:
            logger.info("No questions with invalid difficulty found for %s", subject.name)
            return []

        logger.info(
            "Found %d questions with invalid difficulty for %s",
            len(questions_to_fix),
            subject.name,
        )

        updated = []

        # Process in batches
        for i in range(0, len(questions_to_fix), batch_size):
            batch = questions_to_fix[i : i + batch_size]
            batch_updated = self._fix_difficulty_batch(batch, subject)
            updated.extend(batch_updated)

        return updated

    def _fix_difficulty_batch(
        self,
        questions: list[Question],
        subject: Subject,
    ) -> list[Question]:
        """Fix difficulty for a batch of questions using LLM."""
        # Build prompt with questions
        questions_text = "\n\n".join(
            f"Question {idx + 1} (ID: {q.id}):\n{q.question_text[:500]}"
            for idx, q in enumerate(questions)
        )

        prompt = f"""Analyze these {len(questions)} questions about "{subject.name}" and assign appropriate difficulty levels.

Difficulty levels:
- "beginner": Basic concepts, definitions, simple recall
- "intermediate": Application of concepts, problem-solving, understanding relationships
- "advanced": Complex scenarios, edge cases, optimization, deep understanding

Questions:
{questions_text}

Respond with JSON containing a "difficulties" array with objects for each question:
- id: The question ID (integer)
- difficulty: One of "beginner", "intermediate", or "advanced"
- reason: Brief explanation for the difficulty assignment (1 sentence)

Example:
{{"difficulties": [{{"id": 123, "difficulty": "intermediate", "reason": "Tests application of concepts"}}]}}"""

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message="You are an expert at assessing question difficulty for technical interviews. Respond with valid JSON only.",
                max_tokens=2048,
                temperature=0.3,
            )

            difficulties = response.get("difficulties", [])
            updated = []

            for item in difficulties:
                q_id = item.get("id")
                new_difficulty = item.get("difficulty", "intermediate")

                # Normalize difficulty
                if new_difficulty not in {"beginner", "intermediate", "advanced"}:
                    difficulty_map = {
                        "easy": "beginner",
                        "medium": "intermediate",
                        "hard": "advanced",
                    }
                    new_difficulty = difficulty_map.get(new_difficulty, "intermediate")

                # Find and update the question
                for q in questions:
                    if q.id == q_id:
                        old_difficulty = q.difficulty
                        q.difficulty = new_difficulty
                        q.save(update_fields=["difficulty"])
                        updated.append(q)
                        logger.info(
                            "Updated question %d: %s -> %s",
                            q.id,
                            old_difficulty,
                            new_difficulty,
                        )
                        break

            return updated

        except Exception as e:
            logger.exception("Failed to fix difficulty batch: %s", str(e))
            return []


# Singleton instances per provider
_coverage_services: dict[str | None, InterviewCoverageService] = {}


def get_interview_coverage_service(
    provider: str | None = None,
) -> InterviewCoverageService:
    """Get an interview coverage service instance for the specified provider."""
    global _coverage_services
    if provider not in _coverage_services:
        _coverage_services[provider] = InterviewCoverageService(provider)
    return _coverage_services[provider]
