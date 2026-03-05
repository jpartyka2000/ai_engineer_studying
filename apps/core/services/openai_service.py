"""
OpenAI API service layer.

All OpenAI API interactions should go through this service.
"""

import json
import logging
from typing import Any, Iterator

from django.conf import settings
from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class OpenAIServiceError(Exception):
    """Base exception for OpenAI service errors."""

    pass


class OpenAIAPIError(OpenAIServiceError):
    """Raised when the OpenAI API returns an error."""

    pass


class OpenAIService:
    """
    Centralized service for interacting with the OpenAI API.

    All API calls should go through this service to ensure consistent
    error handling, logging, and configuration.
    """

    def __init__(self) -> None:
        """Initialize the OpenAI API client."""
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    def generate_completion(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a text completion from OpenAI.

        Args:
            prompt: The user prompt to send to OpenAI.
            system_message: Optional system message to set context.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0-2).

        Returns:
            The generated text response.

        Raises:
            OpenAIAPIError: If the API call fails.
        """
        try:
            messages = []

            if system_message:
                messages.append({"role": "system", "content": system_message})

            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_completion_tokens=max_tokens,
                temperature=temperature,
            )

            # Extract text from the response
            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content or ""
            return ""

        except Exception as e:
            logger.exception("OpenAI API error: %s", str(e))
            raise OpenAIAPIError(f"Failed to generate completion: {e}") from e

    def generate_json_completion(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        Generate a JSON completion from OpenAI.

        Args:
            prompt: The user prompt to send to OpenAI.
            system_message: Optional system message to set context.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0-2).

        Returns:
            The parsed JSON response as a dictionary.

        Raises:
            OpenAIAPIError: If the API call fails or JSON parsing fails.
        """
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
        cleaned_response = response.strip()

        # Remove opening code fence
        if cleaned_response.startswith("```"):
            first_newline = cleaned_response.find("\n")
            if first_newline != -1:
                cleaned_response = cleaned_response[first_newline + 1 :]

        # Remove closing code fence
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3].rstrip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response: %s", cleaned_response[:500])
            raise OpenAIAPIError(f"Invalid JSON response from OpenAI: {e}") from e

    def stream_completion(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        conversation_history: list[dict] | None = None,
    ) -> Iterator[str]:
        """
        Stream a text completion from OpenAI.

        Yields text chunks as they arrive from the API.

        Args:
            prompt: The user prompt to send to OpenAI.
            system_message: Optional system message to set context.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0-2).
            conversation_history: Previous messages in format
                [{"role": "user", "content": "..."}, ...].

        Yields:
            Text chunks as strings.

        Raises:
            OpenAIAPIError: If the API call fails.
        """
        try:
            messages = []

            if system_message:
                messages.append({"role": "system", "content": system_message})

            # Add conversation history
            if conversation_history:
                messages.extend(conversation_history)

            messages.append({"role": "user", "content": prompt})

            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_completion_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.exception("OpenAI streaming API error: %s", str(e))
            raise OpenAIAPIError(f"Failed to stream completion: {e}") from e

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
            OpenAIAPIError: If validation fails.
        """
        try:
            return model_class.model_validate(response_data)
        except Exception as e:
            logger.error("Response validation failed: %s", str(e))
            raise OpenAIAPIError(f"Response validation failed: {e}") from e


# Singleton instance for convenience
_openai_service: OpenAIService | None = None


def get_openai_service() -> OpenAIService:
    """Get the singleton OpenAI service instance."""
    global _openai_service
    if _openai_service is None:
        _openai_service = OpenAIService()
    return _openai_service
