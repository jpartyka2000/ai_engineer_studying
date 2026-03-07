"""Service for generating math problems using LLM APIs (Claude or OpenAI)."""

import hashlib
import logging

from pydantic import BaseModel, Field, field_validator

from apps.core.services.llm_service import LLMAPIError, get_llm_service
from apps.equations.models import MathProblem
from apps.subjects.models import Subject

logger = logging.getLogger(__name__)


class GeneratedProblem(BaseModel):
    """A generated math problem from Claude."""

    problem_type: str = Field(description="Type: complete, solve, or mc")
    problem_text: str = Field(description="Plain text description")
    problem_latex: str = Field(description="The equation in LaTeX")
    correct_answer_latex: str = Field(description="Correct answer in LaTeX")
    acceptable_alternatives: list[str] = Field(
        default_factory=list,
        description="Alternative correct forms",
    )
    options: list[str] = Field(
        default_factory=list,
        description="MC options",
    )
    correct_option: str = Field(default="", description="Correct MC option")
    blank_placeholder: str = Field(default="_____", description="Blank placeholder")
    topic: str = Field(description="Specific topic")
    difficulty: str = Field(default="intermediate", description="Difficulty level")
    explanation: str = Field(default="", description="Explanation of answer")
    hints: list[str] = Field(default_factory=list, description="Progressive hints")
    tags: list[str] = Field(default_factory=list, description="Topic tags")

    @field_validator("problem_type", mode="before")
    @classmethod
    def normalize_problem_type(cls, v):
        """Normalize problem type to valid values."""
        if v is None:
            return "complete"
        v = str(v).lower().strip()
        type_map = {
            "complete": "complete",
            "fill": "complete",
            "fill_blank": "complete",
            "solve": "solve",
            "derive": "solve",
            "mc": "mc",
            "multiple_choice": "mc",
            "multiple choice": "mc",
        }
        return type_map.get(v, "complete")

    @field_validator("difficulty", mode="before")
    @classmethod
    def normalize_difficulty(cls, v):
        """Normalize difficulty to valid values."""
        if v is None:
            return "intermediate"
        v = str(v).lower().strip()
        difficulty_map = {
            "easy": "beginner",
            "beginner": "beginner",
            "simple": "beginner",
            "medium": "intermediate",
            "intermediate": "intermediate",
            "hard": "advanced",
            "advanced": "advanced",
            "expert": "advanced",
        }
        return difficulty_map.get(v, "intermediate")


class GeneratedProblemSet(BaseModel):
    """Container for multiple generated problems."""

    problems: list[GeneratedProblem]


class EquationGeneratorService:
    """
    Service for generating math problems using LLM APIs.

    Generates problems for mathematical topics commonly found in
    ML/AI contexts (reinforcement learning, optimization, etc.).
    Supports both Claude and OpenAI as providers.
    """

    SYSTEM_PROMPT = """You are an expert mathematics educator creating practice problems for machine learning and AI topics.

Your task is to generate high-quality mathematical problems that test understanding of key equations and formulas.

Problem Types:
1. "complete" - Fill in the blank: Show an equation with a missing part (marked with _____) that the student must fill in
2. "solve" - Derive/write: Ask the student to write out a complete equation or derivation
3. "mc" - Multiple choice: Provide 4 options where one is correct

Guidelines:
- Use proper LaTeX notation for all mathematical expressions
- For ML topics, include relevant equations like:
  * Bellman equations (Q-learning, value iteration)
  * Policy gradient formulas
  * Loss functions (cross-entropy, MSE)
  * Optimization (gradient descent, Adam)
  * Probability distributions
  * Matrix operations
- Provide clear explanations for why the answer is correct
- Include 2-3 progressive hints for each problem
- Vary difficulty appropriately

You must respond with valid JSON only."""

    def __init__(self, provider: str | None = None) -> None:
        """
        Initialize the generator service.

        Args:
            provider: LLM provider to use ("claude" or "openai").
                     If None, uses the default from settings.
        """
        self.provider = provider
        self.llm = get_llm_service(provider)

    def generate_problems(
        self,
        subject: Subject,
        topic: str,
        problem_type: str = "complete",
        difficulty: str = "intermediate",
        num_problems: int = 5,
    ) -> list[GeneratedProblem]:
        """
        Generate math problems for a specific topic.

        Args:
            subject: The subject area
            topic: Specific topic (e.g., "Bellman Equation")
            problem_type: Type of problems to generate
            difficulty: Difficulty level
            num_problems: Number of problems to generate

        Returns:
            List of generated problems
        """
        type_instructions = {
            "complete": """Generate "complete the equation" problems where students fill in a blank.
Use _____ to indicate the blank. Example:
- problem_latex: "Q(s,a) = r + \\\\gamma \\\\cdot _____"
- correct_answer_latex: "\\\\max_{a'} Q(s', a')"
""",
            "solve": """Generate "derive/solve" problems where students write the full equation.
The problem_latex should describe what to derive. Example:
- problem_text: "Write the Bellman optimality equation for Q-values"
- correct_answer_latex: "Q^*(s,a) = r + \\\\gamma \\\\max_{a'} Q^*(s', a')"
""",
            "mc": """Generate multiple choice problems with 4 options.
- options should be an array of 4 LaTeX strings
- correct_option should be "A", "B", "C", or "D"
""",
        }

        type_instruction = type_instructions.get(problem_type, type_instructions["complete"])

        prompt = f"""Generate {num_problems} math problems about "{topic}" for the subject "{subject.name}".

Problem Type: {problem_type}
Difficulty: {difficulty}

{type_instruction}

Requirements:
- All mathematical expressions must be in valid LaTeX
- Each problem should have:
  * problem_type: "{problem_type}"
  * problem_text: Clear description in plain text
  * problem_latex: The equation (with blank for "complete" type)
  * correct_answer_latex: The correct answer
  * acceptable_alternatives: Array of equivalent correct forms (if any)
  * topic: The specific mathematical topic
  * difficulty: "{difficulty}"
  * explanation: Why this is the correct answer
  * hints: Array of 2-3 progressive hints
  * tags: Relevant topic tags

{"" if problem_type != "mc" else "- options: Array of 4 LaTeX options" + chr(10) + "- correct_option: The correct letter (A/B/C/D)"}

Respond with JSON containing a "problems" array."""

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message=self.SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.7,
            )

            problem_set = GeneratedProblemSet.model_validate(response)
            return problem_set.problems

        except Exception as e:
            logger.exception("Failed to generate math problems: %s", str(e))
            raise LLMAPIError(f"Problem generation failed: {e}") from e

    def save_problems(
        self,
        problems: list[GeneratedProblem],
        subject: Subject,
    ) -> list[MathProblem]:
        """
        Save generated problems to the database.

        Args:
            problems: List of generated problems
            subject: The subject these problems belong to

        Returns:
            List of saved MathProblem instances
        """
        saved = []

        for gen_p in problems:
            # Generate hash for deduplication
            content = f"{subject.id}:{gen_p.topic}:{gen_p.problem_latex}:{gen_p.correct_answer_latex}"
            source_hash = hashlib.sha256(content.encode()).hexdigest()

            # Check if exists
            if MathProblem.objects.filter(
                subject=subject,
                problem_latex=gen_p.problem_latex,
                correct_answer_latex=gen_p.correct_answer_latex,
            ).exists():
                logger.info("Problem already exists: %s", gen_p.topic)
                continue

            problem = MathProblem.objects.create(
                subject=subject,
                problem_type=gen_p.problem_type,
                difficulty=gen_p.difficulty,
                problem_text=gen_p.problem_text,
                problem_latex=gen_p.problem_latex,
                blank_placeholder=gen_p.blank_placeholder,
                correct_answer_latex=gen_p.correct_answer_latex,
                acceptable_alternatives=gen_p.acceptable_alternatives,
                options=gen_p.options,
                correct_option=gen_p.correct_option,
                topic=gen_p.topic,
                explanation=gen_p.explanation,
                hints=gen_p.hints,
                tags=gen_p.tags,
                source=MathProblem.Source.CLAUDE_API,
            )
            saved.append(problem)
            logger.info("Saved math problem: %s", problem.topic)

        return saved


# Cache for generator instances by provider
_generators: dict[str | None, EquationGeneratorService] = {}


def get_equation_generator(provider: str | None = None) -> EquationGeneratorService:
    """
    Get an equation generator instance for the specified provider.

    Args:
        provider: LLM provider to use ("claude" or "openai").
                 If None, uses the default from settings.

    Returns:
        EquationGeneratorService instance.
    """
    if provider not in _generators:
        _generators[provider] = EquationGeneratorService(provider)
    return _generators[provider]
