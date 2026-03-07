"""Pydantic models for coding challenge data validation."""

from pydantic import BaseModel, Field, field_validator


class GeneratedTestCase(BaseModel):
    """Schema for a generated test case."""

    name: str = Field(default="Test", description="Descriptive test name")
    test_type: str = Field(
        default="return",
        description="Type: 'return' for return value, 'stdout' for output, 'assert' for custom assertion",
    )
    function_name: str = Field(
        default="solution", description="Name of the function to test"
    )
    input_data: dict = Field(
        default_factory=dict, description="Keyword arguments to pass to function"
    )
    expected_output: object = Field(
        default=None, description="Expected return value or stdout"
    )
    is_hidden: bool = Field(
        default=False, description="Hidden tests shown only after submission"
    )
    is_sample: bool = Field(
        default=False, description="Sample tests shown in problem description"
    )

    @field_validator("input_data", mode="before")
    @classmethod
    def ensure_dict(cls, v):
        """Ensure input_data is a dict."""
        if v is None:
            return {}
        return v


class GeneratedChallenge(BaseModel):
    """Schema for a Claude-generated coding challenge."""

    title: str = Field(description="Brief descriptive title")
    description: str = Field(description="Full problem description with requirements")
    challenge_type: str = Field(description="Either 'implement' or 'modify'")
    language: str = Field(default="python", description="Programming language")
    starter_code: str = Field(
        default="", description="Initial code (required for modify type)"
    )
    reference_solution: str = Field(default="", description="Reference solution")
    evaluation_criteria: list[str] = Field(
        default_factory=list, description="Specific criteria to evaluate against"
    )
    expected_output: str = Field(default="", description="Expected behavior description")
    hints: list[str] = Field(default_factory=list, description="Progressive hints")
    difficulty: str = Field(
        default="intermediate", description="beginner/intermediate/advanced"
    )
    tags: list[str] = Field(default_factory=list, description="Topic tags")
    estimated_time_minutes: int = Field(
        default=15, description="Estimated completion time"
    )
    test_cases: list[GeneratedTestCase] = Field(
        default_factory=list, description="Test cases for automated validation"
    )


class GeneratedChallengeSet(BaseModel):
    """Container for multiple generated challenges."""

    challenges: list[GeneratedChallenge]


class EvaluationCategory(BaseModel):
    """Schema for an evaluation category."""

    score: int = Field(ge=0, le=100, description="Score out of 100")
    feedback: str = Field(description="Specific feedback for this category")


class CodeEvaluation(BaseModel):
    """Schema for Claude's code evaluation response."""

    is_correct: bool = Field(description="Whether solution is functionally correct")
    overall_score: int = Field(ge=0, le=100, description="Overall score")

    # Category scores
    correctness: EvaluationCategory = Field(
        description="Functional correctness evaluation"
    )
    style: EvaluationCategory = Field(description="Code style/conventions evaluation")
    completeness: EvaluationCategory = Field(
        description="Solution completeness evaluation"
    )
    efficiency: EvaluationCategory = Field(
        description="Algorithmic efficiency evaluation"
    )

    # Feedback
    summary_feedback: str = Field(description="High-level summary")
    detailed_feedback: str = Field(
        description="Detailed explanation with line references"
    )
    areas_for_improvement: list[str] = Field(
        default_factory=list, description="Specific improvement suggestions"
    )
    strengths: list[str] = Field(default_factory=list, description="Things done well")
