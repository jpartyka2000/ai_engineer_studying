"""Service for managing interviewer conversation in system design sessions."""

import logging
from typing import Iterator

from apps.core.services.llm_service import LLMAPIError, get_llm_service
from apps.systemdesign.models import (
    DiagramAnalysis,
    SystemDesignMessage,
    SystemDesignSession,
)

from .challenge_service import ChallengeService

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for managing the LLM interviewer conversation."""

    def __init__(self, provider: str | None = None) -> None:
        """Initialize the conversation service."""
        self.llm = get_llm_service(provider)
        self.challenge_service = ChallengeService(provider)

    def get_interviewer_system_prompt(self, session: SystemDesignSession) -> str:
        """
        Build the system prompt for the interviewer based on session context.

        Args:
            session: The current session.

        Returns:
            System prompt string.
        """
        return self.challenge_service.get_interviewer_system_prompt(
            challenge_title=session.effective_challenge_title,
            description=session.effective_description,
            functional_requirements=session.effective_functional_requirements,
            non_functional_requirements=session.effective_non_functional_requirements,
            constraints=session.effective_constraints,
        )

    def generate_initial_message(self, session: SystemDesignSession) -> str:
        """
        Generate the interviewer's opening message.

        Args:
            session: The session to generate the message for.

        Returns:
            The initial interviewer message.
        """
        prompt = f"""Start the interview for "{session.effective_challenge_title}".

Briefly introduce the challenge (don't repeat all the requirements, just summarize) and ask the candidate their first clarifying question to understand the scope.

Keep it to 3-4 sentences. Be friendly and professional."""

        try:
            response = self.llm.generate_completion(
                prompt=prompt,
                system_message=self.get_interviewer_system_prompt(session),
                max_tokens=500,
                temperature=0.7,
            )
            return response.strip()

        except Exception as e:
            logger.exception("Failed to generate initial message: %s", str(e))
            # Fallback to a generic opening
            return f"""Welcome! Today we'll be designing **{session.effective_challenge_title}**.

I'll let you drive the discussion, but I'll ask clarifying questions along the way. Before we dive into the architecture, let's make sure we understand the requirements.

What aspects of the problem would you like to clarify first?"""

    def stream_response(
        self,
        session: SystemDesignSession,
        user_message: str,
        message_type: str = "general",
        include_diagram_context: bool = False,
    ) -> Iterator[str]:
        """
        Stream the interviewer's response to a user message.

        Args:
            session: The current session.
            user_message: The user's message.
            message_type: Type of message (general, clarification, hint, analysis).
            include_diagram_context: Whether to include diagram analysis in context.

        Yields:
            Text chunks as they arrive.

        Raises:
            LLMAPIError: If the LLM call fails.
        """
        system_prompt = self.get_interviewer_system_prompt(session)

        # Add message type-specific instructions
        if message_type == "hint":
            system_prompt += """

## Special Instruction
The candidate is requesting a hint. Provide a helpful hint that guides them in the right direction WITHOUT giving away the full answer. Use phrases like:
- "Consider what happens when..."
- "Think about how you might handle..."
- "One approach many systems use is..."
- "What if the scale increases to..."
"""

        elif message_type == "clarification":
            system_prompt += """

## Special Instruction
The candidate is asking for clarification on the requirements. Answer their question directly and concisely, then ask a follow-up to keep the interview moving."""

        # Include diagram context if requested and available
        if include_diagram_context:
            latest_analysis = session.analyses.order_by("-created_at").first()
            if latest_analysis:
                components = ", ".join(latest_analysis.identified_components) or "none identified"
                system_prompt += f"""

## Current Diagram State
Components in their diagram: {components}
Overall impression: {latest_analysis.overall_impression or 'No analysis yet'}"""

        # Get conversation history
        conversation_history = session.get_conversation_history(max_tokens=30000)

        try:
            for chunk in self.llm.stream_completion(
                prompt=user_message,
                system_message=system_prompt,
                conversation_history=conversation_history,
                max_tokens=1000,
                temperature=0.7,
            ):
                yield chunk

        except Exception as e:
            logger.exception("Failed to stream response: %s", str(e))
            raise LLMAPIError(f"Failed to generate response: {e}") from e

    def generate_followup_questions(
        self,
        session: SystemDesignSession,
        analysis: DiagramAnalysis,
    ) -> list[str]:
        """
        Generate probing questions based on the current diagram state.

        Args:
            session: The current session.
            analysis: The latest diagram analysis.

        Returns:
            List of follow-up questions to ask.
        """
        components = ", ".join(analysis.identified_components) or "no components"
        concerns = "\n".join(f"- {c}" for c in analysis.concerns) or "none identified"

        prompt = f"""Based on the candidate's current system design diagram for "{session.effective_challenge_title}", generate 2-3 probing interview questions.

Current components in diagram: {components}

Identified concerns:
{concerns}

Generate questions that:
1. Address the concerns identified
2. Push the candidate to think about scalability, reliability, or performance
3. Explore trade-offs in their design choices

Respond with a JSON array of question strings:
["Question 1?", "Question 2?", "Question 3?"]"""

        try:
            response = self.llm.generate_json_completion(
                prompt=prompt,
                system_message="You are an expert system design interviewer. Generate insightful questions.",
                max_tokens=500,
                temperature=0.7,
            )

            if isinstance(response, list):
                return response
            return response.get("questions", [])

        except Exception as e:
            logger.exception("Failed to generate follow-up questions: %s", str(e))
            return []


# Singleton instance
_conversation_service: ConversationService | None = None


def get_conversation_service(provider: str | None = None) -> ConversationService:
    """Get the conversation service singleton."""
    global _conversation_service
    if _conversation_service is None:
        _conversation_service = ConversationService(provider)
    return _conversation_service
