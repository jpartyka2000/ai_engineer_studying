"""Service for scoring completed system design sessions."""

import logging
from typing import Any

from django.conf import settings

from apps.core.services.llm_service import LLMAPIError, get_llm_service
from apps.systemdesign.models import (
    DiagramAnalysis,
    SystemDesignScore,
    SystemDesignSession,
)

logger = logging.getLogger(__name__)


class ScoringService:
    """Service for scoring completed system design sessions."""

    SCORING_PROMPT_TEMPLATE = """You are an expert system design interviewer evaluating a candidate's performance.

## Challenge: {challenge_title}

### Requirements:
**Functional:**
{functional_requirements}

**Non-Functional:**
{non_functional_requirements}

**Constraints:**
{constraints}

{reference_section}

## Candidate's Final Diagram Analysis:
**Components identified:** {components}
**Connections:** {connections}
**Diagram strengths:** {diagram_strengths}
**Diagram concerns:** {diagram_concerns}

## Conversation Summary:
The candidate had {message_count} exchanges with the interviewer.

Key conversation points:
{conversation_summary}

## Scoring Task:
Evaluate the candidate on each criterion (1-10 scale where 1=poor, 5=adequate, 10=excellent):

1. **Scalability (1-10)**: Did they design for scale? Consider: horizontal scaling, load balancing, caching, sharding, etc.

2. **Reliability (1-10)**: Is the system fault-tolerant? Consider: redundancy, failover, data replication, circuit breakers, etc.

3. **Performance (1-10)**: Will it be fast? Consider: latency optimization, CDN, caching layers, async processing, etc.

4. **Cost Efficiency (1-10)**: Is it practical? Consider: not over-engineered, appropriate technology choices, managed services where sensible.

5. **Communication (1-10)**: How well did they communicate? Consider: asking clarifying questions, explaining trade-offs, thinking out loud, responding to feedback.

Respond with JSON:
{{
    "scalability_score": <1-10>,
    "scalability_feedback": "<specific feedback>",
    "reliability_score": <1-10>,
    "reliability_feedback": "<specific feedback>",
    "performance_score": <1-10>,
    "performance_feedback": "<specific feedback>",
    "cost_efficiency_score": <1-10>,
    "cost_efficiency_feedback": "<specific feedback>",
    "communication_score": <1-10>,
    "communication_feedback": "<specific feedback>",
    "strengths_narrative": "<overall strengths - 2-3 sentences>",
    "weaknesses_narrative": "<areas for improvement - 2-3 sentences>",
    "design_coherence_feedback": "<how well components work together - 1-2 sentences>",
    "comparison_to_reference": "<how it compares to ideal solution - 2-3 sentences>"
}}"""

    def __init__(self, provider: str | None = None) -> None:
        """Initialize the scoring service."""
        self.llm = get_llm_service(provider)
        self.provider = provider

    def score_session(self, session: SystemDesignSession) -> SystemDesignScore:
        """
        Generate final scores for a completed session.

        Args:
            session: The session to score.

        Returns:
            SystemDesignScore instance with detailed feedback.

        Raises:
            LLMAPIError: If scoring fails.
        """
        # Get the final analysis (or most recent)
        final_analysis = session.analyses.filter(
            analysis_type=DiagramAnalysis.AnalysisType.FINAL
        ).first()

        if not final_analysis:
            final_analysis = session.analyses.order_by("-created_at").first()

        # Build the scoring prompt
        prompt = self._build_scoring_prompt(session, final_analysis)

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message="You are a fair but thorough system design interviewer. Provide honest, constructive feedback.",
                max_tokens=2048,
                temperature=0.3,  # Low temperature for consistent scoring
            )

            # Create score record
            score = SystemDesignScore.objects.create(
                session=session,
                scalability_score=self._clamp_score(response.get("scalability_score", 5)),
                reliability_score=self._clamp_score(response.get("reliability_score", 5)),
                performance_score=self._clamp_score(response.get("performance_score", 5)),
                cost_efficiency_score=self._clamp_score(response.get("cost_efficiency_score", 5)),
                communication_score=self._clamp_score(response.get("communication_score", 5)),
                strengths_narrative=response.get("strengths_narrative", ""),
                weaknesses_narrative=response.get("weaknesses_narrative", ""),
                design_coherence_feedback=response.get("design_coherence_feedback", ""),
                comparison_to_reference=response.get("comparison_to_reference", ""),
                detailed_feedback={
                    "scalability_feedback": response.get("scalability_feedback", ""),
                    "reliability_feedback": response.get("reliability_feedback", ""),
                    "performance_feedback": response.get("performance_feedback", ""),
                    "cost_efficiency_feedback": response.get("cost_efficiency_feedback", ""),
                    "communication_feedback": response.get("communication_feedback", ""),
                },
                scoring_model_used=self._get_model_name(),
            )

            # Mark session as completed
            session.end_session(SystemDesignSession.Status.COMPLETED)

            return score

        except Exception as e:
            logger.exception("Failed to score session: %s", str(e))
            raise LLMAPIError(f"Scoring failed: {e}") from e

    def _build_scoring_prompt(
        self,
        session: SystemDesignSession,
        analysis: DiagramAnalysis | None,
    ) -> str:
        """Build the scoring prompt with all context."""
        # Format requirements
        fr = "\n".join(f"- {r}" for r in session.effective_functional_requirements) or "Not specified"
        nfr = "\n".join(f"- {r}" for r in session.effective_non_functional_requirements) or "Not specified"
        constraints = "\n".join(f"- {c}" for c in session.effective_constraints) or "Not specified"

        # Reference solution (if pre-defined challenge)
        reference_section = ""
        if session.challenge and session.challenge.reference_solution_description:
            reference_section = f"""
## Reference Solution (for comparison):
**Expected components:** {', '.join(session.challenge.reference_components)}

**Ideal approach:**
{session.challenge.reference_solution_description}
"""

        # Analysis data
        if analysis:
            components = ", ".join(analysis.identified_components) or "None identified"
            connections = str(analysis.identified_connections) if analysis.identified_connections else "None identified"
            diagram_strengths = "\n".join(f"- {s}" for s in analysis.strengths) or "None noted"
            diagram_concerns = "\n".join(f"- {c}" for c in analysis.concerns) or "None noted"
        else:
            components = "No diagram analysis available"
            connections = "N/A"
            diagram_strengths = "N/A"
            diagram_concerns = "N/A"

        # Conversation summary
        messages = session.messages.order_by("created_at")
        message_count = messages.count()

        # Extract key points from conversation
        conversation_points = []
        for msg in messages[:20]:  # Limit to first 20 messages for summary
            if msg.role == "user":
                preview = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
                if msg.message_type == "hint":
                    conversation_points.append(f"- [Hint request] {preview}")
                elif msg.message_type == "clarification":
                    conversation_points.append(f"- [Clarification] {preview}")
                else:
                    conversation_points.append(f"- [User] {preview}")

        conversation_summary = "\n".join(conversation_points) or "No conversation recorded"

        return self.SCORING_PROMPT_TEMPLATE.format(
            challenge_title=session.effective_challenge_title,
            functional_requirements=fr,
            non_functional_requirements=nfr,
            constraints=constraints,
            reference_section=reference_section,
            components=components,
            connections=connections,
            diagram_strengths=diagram_strengths,
            diagram_concerns=diagram_concerns,
            message_count=message_count,
            conversation_summary=conversation_summary,
        )

    def _clamp_score(self, score: Any) -> int:
        """Clamp a score value to 1-10 range."""
        try:
            value = int(score)
            return max(1, min(10, value))
        except (TypeError, ValueError):
            return 5

    def _get_model_name(self) -> str:
        """Get the name of the model being used for scoring."""
        if self.provider == "openai":
            return getattr(settings, "OPENAI_MODEL", "gpt-4")
        return getattr(settings, "CLAUDE_MODEL", "claude-3-opus")


# Singleton instance
_scoring_service: ScoringService | None = None


def get_scoring_service(provider: str | None = None) -> ScoringService:
    """Get the scoring service singleton."""
    global _scoring_service
    if _scoring_service is None:
        _scoring_service = ScoringService(provider)
    return _scoring_service
