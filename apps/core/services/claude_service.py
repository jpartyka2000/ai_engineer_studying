"""
Claude API service layer.

All Claude API interactions should go through this service.
"""

import logging
from typing import Any

from anthropic import Anthropic
from django.conf import settings
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ClaudeServiceError(Exception):
    """Base exception for Claude service errors."""

    pass


class ClaudeAPIError(ClaudeServiceError):
    """Raised when the Claude API returns an error."""

    pass


class ClaudeService:
    """
    Centralized service for interacting with the Claude API.

    All API calls should go through this service to ensure consistent
    error handling, logging, and configuration.
    """

    def __init__(self) -> None:
        """Initialize the Claude API client."""
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CLAUDE_MODEL

    def generate_completion(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a text completion from Claude.

        Args:
            prompt: The user prompt to send to Claude.
            system_message: Optional system message to set context.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0-1).

        Returns:
            The generated text response.

        Raises:
            ClaudeAPIError: If the API call fails.
        """
        try:
            messages = [{"role": "user", "content": prompt}]

            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": temperature,
            }

            if system_message:
                kwargs["system"] = system_message

            response = self.client.messages.create(**kwargs)

            # Extract text from the response
            if response.content and len(response.content) > 0:
                return response.content[0].text
            return ""

        except Exception as e:
            logger.exception("Claude API error: %s", str(e))
            raise ClaudeAPIError(f"Failed to generate completion: {e}") from e

    def generate_json_completion(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        Generate a JSON completion from Claude.

        Args:
            prompt: The user prompt to send to Claude.
            system_message: Optional system message to set context.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0-1).

        Returns:
            The parsed JSON response as a dictionary.

        Raises:
            ClaudeAPIError: If the API call fails or JSON parsing fails.
        """
        import json

        # Add JSON instruction to system message
        json_system = (system_message or "") + (
            "\n\nYou must respond with valid JSON only. "
            "Do not include any text before or after the JSON."
        )

        response = self.generate_completion(
            prompt=prompt,
            system_message=json_system.strip(),
            max_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response: %s", response[:500])
            raise ClaudeAPIError(f"Invalid JSON response from Claude: {e}") from e

    def validate_response(
        self, response_data: dict[str, Any], model_class: type[BaseModel]
    ) -> BaseModel:
        """
        Validate a JSON response against a Pydantic model.

        Args:
            response_data: The JSON data to validate.
            model_class: The Pydantic model class to validate against.

        Returns:
            The validated Pydantic model instance.

        Raises:
            ClaudeAPIError: If validation fails.
        """
        try:
            return model_class.model_validate(response_data)
        except Exception as e:
            logger.error("Response validation failed: %s", str(e))
            raise ClaudeAPIError(f"Response validation failed: {e}") from e


# Singleton instance for convenience
_claude_service: ClaudeService | None = None


def get_claude_service() -> ClaudeService:
    """Get the singleton Claude service instance."""
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeService()
    return _claude_service
