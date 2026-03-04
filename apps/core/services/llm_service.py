"""
LLM Service abstraction layer.

Provides a common interface for different LLM providers (Claude, OpenAI).
"""

import logging
from typing import Any, Iterator, Protocol

from django.conf import settings
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    """Base exception for LLM service errors."""

    pass


class LLMAPIError(LLMServiceError):
    """Raised when an LLM API returns an error."""

    pass


class LLMService(Protocol):
    """Protocol defining the interface for LLM services."""

    def generate_completion(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Generate a text completion."""
        ...

    def generate_json_completion(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Generate a JSON completion."""
        ...

    def stream_completion(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        conversation_history: list[dict] | None = None,
    ) -> Iterator[str]:
        """Stream a text completion."""
        ...

    def validate_response(
        self, response_data: dict[str, Any], model_class: type[BaseModel]
    ) -> BaseModel:
        """Validate a JSON response against a Pydantic model."""
        ...


def get_llm_service(provider: str | None = None) -> LLMService:
    """
    Get an LLM service instance for the specified provider.

    Args:
        provider: The LLM provider to use ("claude" or "openai").
                 If not specified, uses the LLM_PROVIDER setting.

    Returns:
        An LLM service instance.

    Raises:
        ValueError: If the provider is not supported.
    """
    if provider is None:
        provider = getattr(settings, "LLM_PROVIDER", "claude")

    provider = provider.lower()

    if provider == "claude":
        from apps.core.services.claude_service import get_claude_service

        return get_claude_service()
    elif provider == "openai":
        from apps.core.services.openai_service import get_openai_service

        return get_openai_service()
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def get_provider_name(provider: str | None = None) -> str:
    """
    Get the display name for an LLM provider.

    Args:
        provider: The provider identifier.

    Returns:
        Human-readable provider name.
    """
    if provider is None:
        provider = getattr(settings, "LLM_PROVIDER", "claude")

    provider = provider.lower()

    names = {
        "claude": "Claude (Anthropic)",
        "openai": "OpenAI GPT",
    }
    return names.get(provider, provider)
