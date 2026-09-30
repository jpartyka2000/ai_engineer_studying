"""Custom exception classes for the workspace (Work With Existing Codebase) app.

All of these derive from the project-wide base in ``apps.core.exceptions`` so that
callers can catch ``AIInterviewPrepError`` and handle every application error
uniformly.
"""

from apps.core.exceptions import AIInterviewPrepError


class WorkspaceError(AIInterviewPrepError):
    """Base exception for all workspace-mode errors."""

    pass


class UnsafePathError(WorkspaceError):
    """Raised when a path fails the containment checks in ``services.paths``.

    This is a security boundary, not a convenience check: it guards every path the
    app writes to or deletes, and the file-preview endpoint's user-supplied
    ``?path=`` parameter.
    """

    pass


class NotDeletableError(WorkspaceError):
    """Raised when a directory is not eligible for deletion.

    A workspace directory is only deletable if it carries the sentinel file this
    app wrote, proving we created it, and its owning session is not still running.
    """

    pass


class ManifestError(WorkspaceError):
    """Raised when an exercise template's ``manifest.json`` is missing or invalid."""

    pass


class ScaffoldError(WorkspaceError):
    """Raised when materializing an exercise workspace onto disk fails."""

    pass


class WorkspaceMissingError(WorkspaceError):
    """Raised when a session's workspace directory no longer exists on disk."""

    pass


class GitCommandError(WorkspaceError):
    """Raised when a git subprocess exits non-zero or times out."""

    pass


class PortAllocationError(WorkspaceError):
    """Raised when no free host port can be found in the configured range."""

    pass


class DockerUnavailableError(WorkspaceError):
    """Raised when Docker or Docker Compose is required but not usable."""

    pass


class CaptureError(WorkspaceError):
    """Raised when a submission's work cannot be captured from disk."""

    pass


class CheckExecutionError(WorkspaceError):
    """Raised when an objective acceptance check cannot be executed at all.

    Distinct from a check that runs and *fails*: a failed check is a grading
    signal, whereas this means the harness itself could not produce a verdict.
    """

    pass


class GradingError(WorkspaceError):
    """Raised when a submission cannot be graded."""

    pass
