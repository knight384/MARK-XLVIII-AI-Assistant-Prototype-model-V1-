"""core.sandbox.errors — sandbox-specific errors (Phase 6)."""
from __future__ import annotations


class SandboxError(Exception):
    def __init__(self, message: str, *, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


class SandboxUnavailableError(SandboxError):
    """No real isolation mechanism (e.g. Docker) is available."""


class SandboxTimeoutError(SandboxError):
    pass


class SandboxCancelledError(SandboxError):
    pass
