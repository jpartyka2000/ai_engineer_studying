"""
Custom exception classes for the AI Interview Prep application.

All custom exceptions should be defined here for consistency.
"""


class AIInterviewPrepError(Exception):
    """Base exception for all application-specific errors."""

    pass


class ClaudeServiceError(AIInterviewPrepError):
    """Base exception for Claude service errors."""

    pass


class ClaudeAPIError(ClaudeServiceError):
    """Raised when the Claude API returns an error."""

    pass


class ClaudeRateLimitError(ClaudeServiceError):
    """Raised when the Claude API rate limit is exceeded."""

    pass


class QuestionGenerationError(AIInterviewPrepError):
    """Raised when question generation fails."""

    pass


class SessionError(AIInterviewPrepError):
    """Base exception for session-related errors."""

    pass


class SessionNotFoundError(SessionError):
    """Raised when a session cannot be found."""

    pass


class SessionExpiredError(SessionError):
    """Raised when a session has expired."""

    pass


class SubjectError(AIInterviewPrepError):
    """Base exception for subject-related errors."""

    pass


class SubjectNotFoundError(SubjectError):
    """Raised when a subject cannot be found."""

    pass


class SubjectNotActiveError(SubjectError):
    """Raised when trying to use an inactive subject."""

    pass


class ValidationError(AIInterviewPrepError):
    """Raised when data validation fails."""

    pass
