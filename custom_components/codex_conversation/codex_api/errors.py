"""
Codex API error hierarchy.

Mirrors the ``ApiError`` enum from codex-api/src/error.rs.
"""

from __future__ import annotations


class CodexError(Exception):
    """Base exception for all Codex API errors."""


class CodexApiError(CodexError):
    """HTTP-level error returned by the API (4xx / 5xx)."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"API error {status}: {message}")


class CodexContextWindowExceeded(CodexError):
    """Model context limit reached — fatal, do not retry."""


class CodexQuotaExceeded(CodexError):
    """Quota exhausted — fatal, do not retry."""


class CodexUsageNotIncluded(CodexError):
    """Feature not included in the current subscription plan — fatal."""


class CodexRateLimited(CodexError):
    """Rate limited — retryable after *retry_after* seconds (if provided)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(message)


class CodexServerOverloaded(CodexError):
    """Service temporarily unavailable — retryable."""


class CodexStreamError(CodexError):
    """Low-level streaming or SSE parsing error."""
