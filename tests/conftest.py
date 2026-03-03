"""
Shared pytest fixtures for AI Interview Prep tests.
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a basic authenticated user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpassword123",
    )


@pytest.fixture
def admin_user(db):
    """Create a staff/superuser."""
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="adminpassword123",
    )


@pytest.fixture
def mock_claude_api(monkeypatch):
    """
    Mock the Claude API client for deterministic test responses.

    This fixture patches the Anthropic client to return predictable responses
    without making actual API calls.
    """
    from unittest.mock import MagicMock

    mock_client = MagicMock()

    # Default response for generate_completion
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Mocked Claude response")]
    mock_client.messages.create.return_value = mock_response

    def mock_anthropic(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("anthropic.Anthropic", mock_anthropic)

    return mock_client
