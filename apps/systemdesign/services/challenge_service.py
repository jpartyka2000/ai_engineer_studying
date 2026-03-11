"""Service for managing system design challenges."""

import logging
from typing import Any

from django.db.models import QuerySet

from apps.core.services.llm_service import LLMAPIError, get_llm_service
from apps.systemdesign.models import SystemDesignChallenge

logger = logging.getLogger(__name__)


class ChallengeService:
    """Service for retrieving and generating system design challenges."""

    SURPRISE_CHALLENGE_PROMPT = """Generate a unique system design interview challenge for a {difficulty} level candidate.

The challenge should be:
- Realistic and commonly asked in tech interviews
- Appropriate for {difficulty} difficulty ({"simple system, clear requirements" if difficulty == "beginner" else "complex distributed system" if difficulty == "advanced" else "moderately complex system"})
- Different from common examples like Twitter, URL Shortener, Uber, etc.

Create something creative but practical. Examples of less common but valid challenges:
- Design a collaborative code editor
- Design a food delivery tracking system
- Design a live sports scoreboard
- Design a parking lot management system
- Design a ticket booking system
- Design a content moderation pipeline

Respond with JSON containing:
{{
    "title": "Design [System Name]",
    "description": "Full problem statement explaining what the candidate needs to design (2-3 paragraphs)",
    "functional_requirements": ["requirement 1", "requirement 2", ...],
    "non_functional_requirements": ["scalability requirement", "latency requirement", ...],
    "constraints": ["constraint 1", "constraint 2", ...],
    "reference_components": ["component1", "component2", ...],
    "tags": ["tag1", "tag2", ...]
}}"""

    def __init__(self, provider: str | None = None) -> None:
        """Initialize the challenge service."""
        self.llm = get_llm_service(provider)

    def get_available_challenges(
        self,
        difficulty: str | None = None,
        active_only: bool = True,
    ) -> QuerySet[SystemDesignChallenge]:
        """
        Get available challenges, optionally filtered by difficulty.

        Args:
            difficulty: Filter by difficulty level (beginner, intermediate, advanced).
            active_only: Only return active challenges.

        Returns:
            QuerySet of matching challenges.
        """
        queryset = SystemDesignChallenge.objects.all()

        if active_only:
            queryset = queryset.filter(is_active=True)

        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        return queryset.order_by("difficulty", "title")

    def get_challenge_by_slug(self, slug: str) -> SystemDesignChallenge | None:
        """
        Get a specific challenge by its slug.

        Args:
            slug: The URL-safe identifier.

        Returns:
            The challenge or None if not found.
        """
        try:
            return SystemDesignChallenge.objects.get(slug=slug, is_active=True)
        except SystemDesignChallenge.DoesNotExist:
            return None

    def generate_surprise_challenge(
        self,
        difficulty: str = "intermediate",
    ) -> dict[str, Any]:
        """
        Generate a random challenge using the LLM.

        Args:
            difficulty: The difficulty level for the challenge.

        Returns:
            Dict containing challenge details.

        Raises:
            LLMAPIError: If the LLM call fails.
        """
        prompt = self.SURPRISE_CHALLENGE_PROMPT.format(difficulty=difficulty)

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message="You are an expert system design interviewer. Generate unique, practical interview challenges.",
                max_tokens=2048,
                temperature=0.8,  # Higher temperature for variety
            )

            # Add time limit based on difficulty
            time_limits = {
                "beginner": 900,  # 15 minutes
                "intermediate": 1800,  # 30 minutes
                "advanced": 2700,  # 45 minutes
            }
            response["time_limit_seconds"] = time_limits.get(difficulty, 1800)
            response["difficulty"] = difficulty

            return response

        except Exception as e:
            logger.exception("Failed to generate surprise challenge: %s", str(e))
            raise LLMAPIError(f"Failed to generate challenge: {e}") from e

    def get_interviewer_system_prompt(
        self,
        challenge_title: str,
        description: str,
        functional_requirements: list[str],
        non_functional_requirements: list[str],
        constraints: list[str],
    ) -> str:
        """
        Build the system prompt for the LLM interviewer persona.

        Args:
            challenge_title: The title of the challenge.
            description: The full problem description.
            functional_requirements: List of functional requirements.
            non_functional_requirements: List of non-functional requirements.
            constraints: List of constraints.

        Returns:
            System prompt string for the interviewer.
        """
        requirements_text = "\n".join(f"- {r}" for r in functional_requirements)
        nfr_text = "\n".join(f"- {r}" for r in non_functional_requirements)
        constraints_text = "\n".join(f"- {c}" for c in constraints)

        return f"""You are an experienced system design interviewer conducting a technical interview.

## Your Role
- Act as a friendly but thorough interviewer
- Ask clarifying questions to understand the candidate's approach
- Provide hints when the candidate is stuck (but don't give away the answer)
- Challenge assumptions and probe deeper on important topics
- Guide the conversation but let the candidate lead the design

## The Challenge: {challenge_title}

{description}

## Functional Requirements
{requirements_text}

## Non-Functional Requirements
{nfr_text}

## Constraints
{constraints_text}

## Interview Guidelines
1. Start by asking the candidate about their understanding of the problem
2. Encourage them to think out loud
3. Ask about:
   - Scale and traffic estimates
   - Data model design
   - API design
   - High-level architecture
   - Component deep dives
   - Trade-offs and alternatives
4. When they add components to their diagram, ask why they chose that approach
5. Probe for:
   - Single points of failure
   - Scalability bottlenecks
   - Data consistency issues
   - Performance optimizations

## Communication Style
- Be encouraging but not too easy
- Use phrases like "That's a good start, but consider..." or "What happens if..."
- Ask one question at a time
- Keep responses concise (2-4 sentences usually)
- Reference their diagram when discussing architecture

Remember: You're evaluating both their technical knowledge AND their communication skills."""


# Singleton instance
_challenge_service: ChallengeService | None = None


def get_challenge_service(provider: str | None = None) -> ChallengeService:
    """Get the challenge service singleton."""
    global _challenge_service
    if _challenge_service is None:
        _challenge_service = ChallengeService(provider)
    return _challenge_service
