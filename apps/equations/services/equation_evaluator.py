"""Service for evaluating mathematical answers using LLM APIs (Claude or OpenAI)."""

import logging

from django.utils import timezone
from pydantic import BaseModel, Field, field_validator

from apps.core.services.llm_service import LLMAPIError, get_llm_service
from apps.equations.models import MathAnswer, MathProblem

logger = logging.getLogger(__name__)


class EvaluationResult(BaseModel):
    """Result of evaluating a mathematical answer."""

    is_correct: bool = Field(description="Whether the answer is fully correct")
    partial_credit: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Partial credit score (0.0 to 1.0)",
    )
    feedback: str = Field(description="Feedback for the student")
    mathematical_errors: list[str] = Field(
        default_factory=list,
        description="List of specific mathematical errors",
    )

    @field_validator("partial_credit", mode="before")
    @classmethod
    def normalize_partial_credit(cls, v):
        """Ensure partial credit is in valid range."""
        if v is None:
            return 0.0
        v = float(v)
        return max(0.0, min(1.0, v))


class EquationEvaluatorService:
    """
    Service for evaluating mathematical answers using LLM APIs.

    Checks if user's LaTeX answer is mathematically equivalent to the
    expected answer, considering equivalent forms and LaTeX formatting variations.
    Supports both Claude and OpenAI as providers.
    """

    SYSTEM_PROMPT = """You are a mathematics professor evaluating student answers to mathematical equations.

Your task is to evaluate whether the student's answer is mathematically correct, considering:
1. Mathematical equivalence (e.g., x+1 and 1+x are equivalent)
2. Different but valid forms (e.g., 2/4 and 1/2 are equivalent)
3. LaTeX formatting variations (e.g., \\frac{1}{2} and 1/2 may represent the same value)

Guidelines:
- Be lenient with LaTeX formatting differences that don't change the mathematical meaning
- Award partial credit for answers that show correct understanding but have minor errors
- Identify specific mathematical errors clearly
- Provide constructive feedback that helps the student learn

You must respond with valid JSON only."""

    def __init__(self, provider: str | None = None) -> None:
        """
        Initialize the evaluator service.

        Args:
            provider: LLM provider to use ("claude" or "openai").
                     If None, uses the default from settings.
        """
        self.provider = provider
        self.llm = get_llm_service(provider)

    def evaluate_answer(
        self,
        problem: MathProblem,
        user_answer_latex: str,
        selected_option: str = "",
    ) -> EvaluationResult:
        """
        Evaluate a user's mathematical answer.

        Args:
            problem: The math problem being answered
            user_answer_latex: The user's answer in LaTeX format
            selected_option: For MC problems, the selected option letter

        Returns:
            EvaluationResult with correctness and feedback
        """
        # Handle multiple choice problems
        if problem.problem_type == MathProblem.ProblemType.MULTIPLE_CHOICE:
            return self._evaluate_multiple_choice(problem, selected_option)

        # For complete and solve problems, use LLM
        return self._evaluate_with_llm(problem, user_answer_latex)

    def _evaluate_multiple_choice(
        self,
        problem: MathProblem,
        selected_option: str,
    ) -> EvaluationResult:
        """Evaluate a multiple choice answer."""
        is_correct = selected_option.upper() == problem.correct_option.upper()

        if is_correct:
            feedback = "Correct! Well done."
            partial_credit = 1.0
        else:
            correct_idx = ord(problem.correct_option.upper()) - ord("A")
            if 0 <= correct_idx < len(problem.options):
                correct_answer = problem.options[correct_idx]
                feedback = f"Incorrect. The correct answer is {problem.correct_option}: {correct_answer}"
            else:
                feedback = f"Incorrect. The correct answer is {problem.correct_option}."
            partial_credit = 0.0

        if problem.explanation:
            feedback += f"\n\nExplanation: {problem.explanation}"

        return EvaluationResult(
            is_correct=is_correct,
            partial_credit=partial_credit,
            feedback=feedback,
            mathematical_errors=[],
        )

    def _evaluate_with_llm(
        self,
        problem: MathProblem,
        user_answer_latex: str,
    ) -> EvaluationResult:
        """Evaluate an answer using LLM for mathematical equivalence."""
        # Build context based on problem type
        if problem.problem_type == MathProblem.ProblemType.COMPLETE:
            problem_context = f"""Problem Type: Complete the equation
Problem: {problem.problem_text}
Equation with blank: {problem.problem_latex}
The blank placeholder is: {problem.blank_placeholder}
Correct answer for the blank: {problem.correct_answer_latex}"""
        else:  # SOLVE
            problem_context = f"""Problem Type: Solve from scratch
Problem: {problem.problem_text}
Expected equation/solution: {problem.correct_answer_latex}"""

        # Add acceptable alternatives if any
        if problem.acceptable_alternatives:
            alts = ", ".join(problem.acceptable_alternatives)
            problem_context += f"\nAcceptable alternative forms: {alts}"

        prompt = f"""{problem_context}

Student's answer (in LaTeX): {user_answer_latex}

Evaluate the student's answer and respond with JSON containing:
- is_correct: boolean - true if mathematically correct/equivalent
- partial_credit: float 0.0-1.0 - give partial credit for close answers
- feedback: string - constructive feedback for the student
- mathematical_errors: array of strings - specific errors found (empty if correct)

Consider:
1. Is the answer mathematically equivalent to the expected answer?
2. Are there any mathematical errors in reasoning or notation?
3. If partially correct, what proportion of credit should be awarded?
4. What feedback would help the student understand?"""

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message=self.SYSTEM_PROMPT,
                max_tokens=1024,
                temperature=0.3,
            )

            result = EvaluationResult.model_validate(response)

            # Add explanation if available and answer is wrong
            if not result.is_correct and problem.explanation:
                result.feedback += f"\n\nNote: {problem.explanation}"

            return result

        except Exception as e:
            logger.exception("Failed to evaluate math answer: %s", str(e))
            raise LLMAPIError(f"Evaluation failed: {e}") from e

    def save_evaluation(
        self,
        answer: MathAnswer,
        result: EvaluationResult,
    ) -> MathAnswer:
        """
        Save evaluation results to a MathAnswer instance.

        Args:
            answer: The MathAnswer to update
            result: The evaluation result

        Returns:
            Updated MathAnswer instance
        """
        answer.is_correct = result.is_correct
        answer.partial_credit = result.partial_credit
        answer.feedback = result.feedback
        answer.mathematical_errors = result.mathematical_errors
        answer.evaluated_at = timezone.now()
        answer.save()

        return answer


# Cache for evaluator instances by provider
_evaluators: dict[str | None, EquationEvaluatorService] = {}


def get_equation_evaluator(provider: str | None = None) -> EquationEvaluatorService:
    """
    Get an equation evaluator instance for the specified provider.

    Args:
        provider: LLM provider to use ("claude" or "openai").
                 If None, uses the default from settings.

    Returns:
        EquationEvaluatorService instance.
    """
    if provider not in _evaluators:
        _evaluators[provider] = EquationEvaluatorService(provider)
    return _evaluators[provider]
