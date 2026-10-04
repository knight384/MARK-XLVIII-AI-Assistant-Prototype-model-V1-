"""core.tools.errors — tool-specific error taxonomy (Phase 3 spec, Part 24)."""
from __future__ import annotations


class ToolError(Exception):
    def __init__(self, message: str, *, tool_name: str | None = None, cause: Exception | None = None):
        super().__init__(message)
        self.tool_name = tool_name
        self.cause = cause


class ToolNotFoundError(ToolError):
    pass


class ToolValidationError(ToolError):
    pass


class ToolExecutionError(ToolError):
    pass


class ToolTimeoutError(ToolError):
    pass


class ToolCancelledError(ToolError):
    pass


class ToolVerificationError(ToolError):
    pass


class ToolRegistrationError(ToolError):
    pass
