"""Service for ranking questions by interview importance using LLM."""

import json
import logging
from datetime import date

from pydantic import BaseModel, Field

from apps.core.services.llm_service import LLMAPIError, LLMService, get_llm_service

logger = logging.getLogger(__name__)


class QuestionForRanking(BaseModel):
    """Question data sent to LLM for ranking."""

    id: int
    question_text: str
    options: list[str] = Field(default_factory=list)
    difficulty: str
    tags: list[str] = Field(default_factory=list)


class RankedQuestion(BaseModel):
    """Single ranked question from LLM response."""

    id: int
    rank: int = Field(description="1 = most important for interviews")
    relevance_score: float = Field(ge=0.0, le=1.0, description="0-1 interview relevance")
    reason: str = Field(description="Brief reason for ranking")


class RankingResponse(BaseModel):
    """LLM ranking response."""

    ranked_questions: list[RankedQuestion]


class InterviewQuestionRankerService:
    """
    Service for ranking questions by interview importance using LLM.

    This service analyzes exam questions and ranks them based on their
    relevance and importance for AI/ML engineer interviews.
    """

    SYSTEM_PROMPT = """You are an expert AI/ML engineering interviewer with deep knowledge of what skills and concepts are tested in real interviews at top tech companies.

Your task is to rank exam questions by their importance and relevance for AI/ML engineer interviews.

Consider these factors when ranking:
1. How commonly is this topic asked in real interviews?
2. Does this question test practical, applicable knowledge vs. obscure trivia?
3. Is this a "must-know" concept that any qualified candidate should understand?
4. Would a hiring manager be concerned if a candidate missed this?
5. Does this align with current industry practices and trends?

Today's date is {current_date}. Consider recent industry trends, emerging technologies, and what skills are currently in high demand for AI/ML roles.

You must respond with valid JSON only."""

    def __init__(self, provider: str | None = None) -> None:
        """
        Initialize the interview question ranker service.

        Args:
            provider: The LLM provider to use ("claude" or "openai").
                     If not specified, uses the LLM_PROVIDER setting.
        """
        self.provider = provider
        self.llm: LLMService = get_llm_service(provider)

    def rank_questions(
        self,
        questions: list[QuestionForRanking],
        subject_name: str,
        num_to_select: int,
        current_date: date | None = None,
    ) -> list[int]:
        """
        Rank questions by interview importance and return selected IDs.

        Args:
            questions: List of questions to rank (max 50, full text + options).
            subject_name: Name of the subject for context.
            num_to_select: How many top questions to return.
            current_date: Date for time-awareness (defaults to today).

        Returns:
            List of question IDs in ranked order (most important first).

        Raises:
            LLMAPIError: If the ranking fails.
            ValueError: If questions list is empty.
        """
        if not questions:
            raise ValueError("Questions list cannot be empty")

        if current_date is None:
            current_date = date.today()

        # Prepare questions data for prompt
        questions_data = [
            {
                "id": q.id,
                "question": q.question_text[:500],  # Truncate long questions
                "options": q.options[:4] if q.options else [],
                "difficulty": q.difficulty,
                "tags": q.tags[:5] if q.tags else [],
            }
            for q in questions
        ]

        prompt = f"""Analyze and rank the following {len(questions)} questions about "{subject_name}" based on their importance for AI/ML engineer interviews.

Today's date is {current_date.isoformat()}.

Select the top {num_to_select} questions that are MOST critical for interview preparation. Focus on questions that:
- Test fundamental concepts that interviewers commonly ask about
- Demonstrate practical knowledge applicable to real work
- Cover topics where knowledge gaps would be most damaging in an interview

Questions to analyze:
{json.dumps(questions_data, indent=2)}

Respond with a JSON object containing a "ranked_questions" array. Include ONLY the top {num_to_select} most important questions. Each entry should have:
- "id": The question ID (integer)
- "rank": Position from 1 to {num_to_select} (1 = most important)
- "relevance_score": A score from 0.0 to 1.0 indicating interview relevance
- "reason": A brief explanation (1 sentence) of why this question is important

Example response format:
{{
  "ranked_questions": [
    {{"id": 123, "rank": 1, "relevance_score": 0.95, "reason": "Core concept frequently asked in interviews"}},
    {{"id": 456, "rank": 2, "relevance_score": 0.90, "reason": "Practical skill tested in coding rounds"}}
  ]
}}"""

        system_message = self.SYSTEM_PROMPT.format(current_date=current_date.isoformat())

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message=system_message,
                max_tokens=2048,
                temperature=0.3,  # Lower temperature for more deterministic ranking
            )

            # Validate response
            ranking_response = RankingResponse.model_validate(response)

            # Extract IDs in ranked order
            sorted_questions = sorted(
                ranking_response.ranked_questions, key=lambda q: q.rank
            )
            ranked_ids = [q.id for q in sorted_questions]

            # Validate that returned IDs exist in our input
            valid_input_ids = {q.id for q in questions}
            valid_ranked_ids = [qid for qid in ranked_ids if qid in valid_input_ids]

            if len(valid_ranked_ids) < len(ranked_ids):
                logger.warning(
                    "LLM returned %d invalid question IDs, filtered to %d valid",
                    len(ranked_ids) - len(valid_ranked_ids),
                    len(valid_ranked_ids),
                )

            if not valid_ranked_ids:
                raise LLMAPIError("LLM returned no valid question IDs")

            logger.info(
                "Ranked %d questions for %s, selected top %d",
                len(questions),
                subject_name,
                len(valid_ranked_ids),
            )

            return valid_ranked_ids

        except LLMAPIError:
            raise
        except Exception as e:
            logger.exception("Failed to rank questions: %s", str(e))
            raise LLMAPIError(f"Question ranking failed: {e}") from e


# Singleton instance
_ranker_service: InterviewQuestionRankerService | None = None


def get_interview_ranker(provider: str | None = None) -> InterviewQuestionRankerService:
    """
    Get the singleton interview ranker service.

    Args:
        provider: The LLM provider to use.

    Returns:
        An InterviewQuestionRankerService instance.
    """
    global _ranker_service
    if _ranker_service is None:
        _ranker_service = InterviewQuestionRankerService(provider)
    return _ranker_service
