"""core.policy.errors — policy/approval-specific errors (Phase 6)."""
from __future__ import annotations


class PolicyError(Exception):
    def __init__(self, message: str, *, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


class PolicyDeniedError(PolicyError):
    """Raised by the ToolExecutor when a PolicyEngine decision is DENY —
    carries the human-readable reason (spec Part 49)."""
    def __init__(self, message: str, reason: str = ""):
        super().__init__(message)
        self.reason = reason


class ApprovalTimeoutError(PolicyError):
    pass


class ApprovalDeniedError(PolicyError):
    def __init__(self, message: str, reason: str = ""):
        super().__init__(message)
        self.reason = reason


class ApprovalNotFoundError(PolicyError):
    pass


class ApprovalMismatchError(PolicyError):
    """Raised when an approval is presented for a different operation than
    the one it was granted for (spec Part 16: binding)."""
