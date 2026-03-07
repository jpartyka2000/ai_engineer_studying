"""
Claude API service layer.

All Claude API interactions should go through this service.
"""

import base64
import logging
from pathlib import Path
from typing import Any, Iterator

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
        import re

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

        # Strip markdown code fences if present
        # Claude sometimes wraps JSON in ```json ... ```
        cleaned_response = response.strip()

        # Remove opening code fence
        if cleaned_response.startswith("```"):
            # Find the end of the first line (the language identifier)
            first_newline = cleaned_response.find("\n")
            if first_newline != -1:
                cleaned_response = cleaned_response[first_newline + 1:]

        # Remove closing code fence
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3].rstrip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response: %s", cleaned_response[:500])
            raise ClaudeAPIError(f"Invalid JSON response from Claude: {e}") from e

    def generate_vision_completion(
        self,
        image_path: Path | str,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a completion from Claude using an image input.

        Args:
            image_path: Path to the image file.
            prompt: The user prompt to send with the image.
            system_message: Optional system message to set context.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0-1).

        Returns:
            The generated text response.

        Raises:
            ClaudeAPIError: If the API call fails.
        """
        try:
            image_path = Path(image_path)

            # Read and encode image
            image_data = image_path.read_bytes()
            base64_image = base64.standard_b64encode(image_data).decode("utf-8")

            # Determine media type from extension
            ext = image_path.suffix.lower()
            media_type_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            media_type = media_type_map.get(ext, "image/png")

            # Build message with image
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ]

            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": temperature,
            }

            if system_message:
                kwargs["system"] = system_message

            response = self.client.messages.create(**kwargs)

            if response.content and len(response.content) > 0:
                return response.content[0].text
            return ""

        except Exception as e:
            logger.exception("Claude Vision API error: %s", str(e))
            raise ClaudeAPIError(f"Failed to generate vision completion: {e}") from e

    def generate_vision_json_completion(
        self,
        image_path: Path | str,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        Generate a JSON completion from Claude using an image input.

        Args:
            image_path: Path to the image file.
            prompt: The user prompt to send with the image.
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

        response = self.generate_vision_completion(
            image_path=image_path,
            prompt=prompt,
            system_message=json_system.strip(),
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Strip markdown code fences if present
        cleaned_response = response.strip()

        if cleaned_response.startswith("```"):
            first_newline = cleaned_response.find("\n")
            if first_newline != -1:
                cleaned_response = cleaned_response[first_newline + 1:]

        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3].rstrip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse vision JSON response: %s", cleaned_response[:500])
            raise ClaudeAPIError(f"Invalid JSON response from Claude vision: {e}") from e

    def stream_completion(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        conversation_history: list[dict] | None = None,
    ) -> Iterator[str]:
        """
        Stream a text completion from Claude.

        Yields text chunks as they arrive from the API. This is useful for
        real-time display of responses in chat interfaces.

        Args:
            prompt: The user prompt to send to Claude (most recent message).
            system_message: Optional system message to set context.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0-1).
            conversation_history: Previous messages in format
                [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...].
                The prompt will be appended as the final user message.

        Yields:
            Text chunks as strings.

        Raises:
            ClaudeAPIError: If the API call fails.
        """
        try:
            # Build messages array
            messages = conversation_history or []
            messages.append({"role": "user", "content": prompt})

            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": temperature,
            }

            if system_message:
                kwargs["system"] = system_message

            # Use streaming API with context manager
            with self.client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield text

        except Exception as e:
            logger.exception("Claude streaming API error: %s", str(e))
            raise ClaudeAPIError(f"Failed to stream completion: {e}") from e

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
