"""
core.tools — the standardized Tool Registry/Executor layer (Phase 3).

Typical usage (main.py):

    from core.tools import get_default_registry, ToolExecutor, ToolContext

    registry = get_default_registry()
    executor = ToolExecutor(registry)
    declarations = registry.generate_gemini_declarations()

    ...

    context = ToolContext(extra={"ui": self.ui, "speak": self.speak, "live": self})
    result = await executor.execute(function_call_name, args, context)
"""
from .base import CancellationToken, Tool, ToolContext, ToolEvent, VerificationResult, default_audit_hook
from .errors import (
    ToolCancelledError, ToolError, ToolExecutionError, ToolNotFoundError,
    ToolRegistrationError, ToolTimeoutError, ToolValidationError, ToolVerificationError,
)
from .executor import ToolExecutor
from .metadata import Capability, RiskLevel, ToolCategory, ToolMetadata
from .registry import ToolRegistry, get_default_registry
from .results import ToolResult
from .schemas import ParamSchema, ToolSchema

__all__ = [
    "Tool", "ToolContext", "CancellationToken", "ToolEvent", "VerificationResult", "default_audit_hook",
    "ToolError", "ToolNotFoundError", "ToolValidationError", "ToolExecutionError",
    "ToolTimeoutError", "ToolCancelledError", "ToolVerificationError", "ToolRegistrationError",
    "ToolExecutor",
    "RiskLevel", "ToolCategory", "Capability", "ToolMetadata",
    "ToolRegistry", "get_default_registry",
    "ToolResult",
    "ParamSchema", "ToolSchema",
]
