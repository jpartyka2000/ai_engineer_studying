"""
Argument mode service layer.

This module handles Claude API integration for the Argument mode,
including generating initial prompts, opponent responses, and
end-of-session analysis.
"""

import logging
from typing import TYPE_CHECKING, Any, Iterator

from apps.core.services.claude_service import ClaudeAPIError, get_claude_service

if TYPE_CHECKING:
    from apps.argument.models import ArgumentSession
    from apps.subjects.models import Subject

logger = logging.getLogger(__name__)


# Heat level persona definitions
HEAT_LEVEL_PERSONAS: dict[str, str] = {
    "friend": """You are a friendly colleague who happens to disagree with the user's position.
You push back constructively but maintain warmth and respect throughout.
Use phrases like "I see your point, but have you considered...", "That's interesting, though I think...",
and "I respect that view, but let me offer another perspective..."
Be supportive even while disagreeing. Acknowledge good points they make.
Your goal is to help them think through the problem, not to win the argument.""",

    "colleague": """You are a professional peer who firmly disagrees with the user's position.
Be direct, persistent, and thorough in your challenges. Remain professional at all times.
Ask probing questions that expose weaknesses in their reasoning.
Use phrases like "I disagree because...", "That doesn't account for...",
and "The evidence suggests otherwise..."
Don't be swayed easily - make them work to defend their position.
You're skeptical but fair, and you'll concede a point if they make a genuinely strong argument.""",

    "jerk": """You are an arrogant, condescending senior engineer who thinks the user is wrong.
Be dismissive of their experience level and question their competence for this role.
Use phrases like "That's a junior mistake...", "Anyone with real experience would know...",
"I can't believe you'd even suggest that...", and "This is why we have code review..."
Reference how things work "in the real world" versus "in tutorials".
Question whether they've actually built production systems.

CRITICAL CONSTRAINTS:
- NEVER use profanity, slurs, or vulgar language
- NEVER make sexual comments or references
- NEVER attack their personal life, family, appearance, or identity
- ONLY criticize their professional abilities, technical knowledge, and workplace standing
- If they mention anything personal, redirect back to the technical argument
- You can say things like "Maybe this role is above your level" or "Have you considered
  a less senior position?" but nothing about their personal worth as a human being.
- Stay within the bounds of a rude but technically-focused colleague.""",
}


DIFFICULTY_CONTEXT: dict[str, str] = {
    "beginner": """The user is at a beginner level. Focus on fundamental concepts and common
misconceptions. Don't assume deep technical knowledge. The debate should center on
basic principles and straightforward scenarios.""",

    "intermediate": """The user is at an intermediate level. You can discuss more nuanced topics,
trade-offs between approaches, and real-world considerations. Expect them to know
the basics but probe their understanding of edge cases and best practices.""",

    "advanced": """The user is at an advanced level. Engage with complex scenarios, architectural
decisions, performance implications, and subtle technical trade-offs. Challenge them
on edge cases, scalability concerns, and industry best practices. Expect sophisticated
arguments and provide sophisticated counterarguments.""",
}


def generate_initial_prompt(subject: "Subject", difficulty: str) -> str:
    """
    Generate an opinionated topic or scenario to start the argument.

    Args:
        subject: The subject area for the argument.
        difficulty: The difficulty level (beginner, intermediate, advanced).

    Returns:
        str: An opinionated prompt asking for the user's position.

    Raises:
        ClaudeAPIError: If the API call fails.
    """
    claude_service = get_claude_service()

    system_message = f"""You are generating a debate topic for a technical argument about {subject.name}.

The user will be challenged to defend their position on this topic.

{DIFFICULTY_CONTEXT.get(difficulty, DIFFICULTY_CONTEXT['intermediate'])}

Generate ONE opinionated statement or scenario that:
1. Is specific to {subject.name}
2. Has legitimate arguments on both sides
3. Would spark an interesting technical debate
4. Is appropriate for the {difficulty} difficulty level

Format your response as a direct question or scenario, for example:
- "Your team lead wants to use X approach for Y problem. What's your take on this?"
- "A colleague argues that X is always better than Y. Do you agree?"
- "You're in a code review and someone suggests Z. How would you respond?"

Keep it concise (2-3 sentences max). End with asking for the user's opinion."""

    prompt = f"Generate a debate topic about {subject.name} at {difficulty} level."

    try:
        return claude_service.generate_completion(
            prompt=prompt,
            system_message=system_message,
            max_tokens=500,
            temperature=0.9,
        )
    except ClaudeAPIError:
        logger.exception("Failed to generate initial prompt")
        raise


def generate_opponent_response(
    session: "ArgumentSession",
    user_message: str,
) -> Iterator[str]:
    """
    Generate the AI opponent's response to the user's argument.

    Streams the response for real-time display.

    Args:
        session: The argument session.
        user_message: The user's latest message.

    Yields:
        str: Text chunks as they arrive from the API.

    Raises:
        ClaudeAPIError: If the API call fails.
    """
    claude_service = get_claude_service()

    heat_persona = HEAT_LEVEL_PERSONAS.get(
        session.heat_level,
        HEAT_LEVEL_PERSONAS["colleague"],
    )
    difficulty_context = DIFFICULTY_CONTEXT.get(
        session.difficulty,
        DIFFICULTY_CONTEXT["intermediate"],
    )

    system_message = f"""You are participating in a technical argument about {session.subject.name}.

{heat_persona}

{difficulty_context}

The debate started with this topic:
"{session.initial_prompt}"

GUIDELINES:
- Challenge their technical points specifically
- Bring up counterexamples, edge cases, or alternative approaches
- If they make a valid point, you can partially acknowledge it but pivot to another angle
- Keep responses focused and concise (3-4 paragraphs max)
- Stay on topic - if they go off-topic, redirect back
- Use technical terminology appropriate for the subject
- End with a question or challenge that pushes them to defend further

Remember: This is a learning exercise. The goal is to make them think critically,
not to be mean-spirited (unless you're in 'jerk' mode, where you can be condescending
about their professional abilities only)."""

    # Build conversation history
    history = session.get_conversation_history()

    try:
        yield from claude_service.stream_completion(
            prompt=user_message,
            system_message=system_message,
            conversation_history=history,
            max_tokens=1500,
            temperature=0.8,
        )
    except ClaudeAPIError:
        logger.exception("Failed to generate opponent response")
        raise


def generate_analysis(session: "ArgumentSession") -> dict[str, Any]:
    """
    Analyze the argument and generate scores and feedback.

    Called when the user ends the argument.

    Args:
        session: The completed argument session.

    Returns:
        dict: Analysis results with scores and feedback.

    Raises:
        ClaudeAPIError: If the API call fails.
    """
    claude_service = get_claude_service()

    # Build the full conversation text for analysis
    conversation_text = f"Topic: {session.initial_prompt}\n\n"
    for msg in session.messages.order_by("created_at"):
        role_label = "USER" if msg.role == "user" else "OPPONENT"
        conversation_text += f"{role_label}: {msg.content}\n\n"

    system_message = """You are an expert technical mentor analyzing a debate between a user and an AI opponent.

Evaluate the USER's performance (not the opponent's) on three dimensions:

1. TECHNICAL CORRECTNESS (1-10):
   - Were their technical claims accurate?
   - Did they demonstrate understanding of the subject?
   - Did they cite relevant concepts, patterns, or best practices?
   - Were there any factual errors or misconceptions?

2. TEMPERAMENT CONTROL (1-10):
   - Did they stay calm and professional?
   - Did they avoid personal attacks or emotional responses?
   - Did they handle provocations gracefully (if any)?
   - Did they focus on the technical merits rather than getting defensive?

3. TOPIC FOCUS (1-10):
   - Did they stay on the original topic?
   - Were their arguments relevant to the debate?
   - Did they avoid going off on tangents?
   - Did they address the opponent's points directly?

Provide your analysis as JSON with this exact structure:
{
    "technical_score": <1-10>,
    "technical_feedback": "<2-3 sentences explaining the score>",
    "temperament_score": <1-10>,
    "temperament_feedback": "<2-3 sentences explaining the score>",
    "focus_score": <1-10>,
    "focus_feedback": "<2-3 sentences explaining the score>",
    "overall_feedback": "<2-3 sentences with overall advice and encouragement>"
}

Be constructive and encouraging while being honest about areas for improvement."""

    prompt = f"""Analyze this technical argument:

{conversation_text}

Provide your analysis as JSON."""

    try:
        result = claude_service.generate_json_completion(
            prompt=prompt,
            system_message=system_message,
            max_tokens=2000,
            temperature=0.3,
        )

        # Validate required fields
        required_fields = [
            "technical_score",
            "technical_feedback",
            "temperament_score",
            "temperament_feedback",
            "focus_score",
            "focus_feedback",
            "overall_feedback",
        ]

        for field in required_fields:
            if field not in result:
                raise ClaudeAPIError(f"Missing required field in analysis: {field}")

        # Ensure scores are within range
        for score_field in ["technical_score", "temperament_score", "focus_score"]:
            score = result[score_field]
            if not isinstance(score, int) or score < 1 or score > 10:
                result[score_field] = max(1, min(10, int(score)))

        return result

    except ClaudeAPIError:
        logger.exception("Failed to generate analysis")
        raise
