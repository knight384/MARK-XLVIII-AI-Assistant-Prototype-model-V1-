"""core.tools.results — standardized ToolResult (Phase 3 spec, Part 10)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    data: Any = None                 # the "normal" return value — usually a string, matching prior behavior
    error: str | None = None
    error_type: str | None = None    # class name of the underlying error, for developer logs
    message: str | None = None       # short human/model-facing message (what gets sent back to Gemini)
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None

    @classmethod
    def ok(cls, tool_name: str, data: Any = None, message: str | None = None,
            metadata: dict | None = None, duration_ms: float | None = None) -> "ToolResult":
        return cls(
            tool_name=tool_name, success=True, data=data,
            message=message if message is not None else (data if isinstance(data, str) else "Done."),
            metadata=metadata or {}, duration_ms=duration_ms,
        )

    @classmethod
    def fail(cls, tool_name: str, error: str, error_type: str | None = None,
             message: str | None = None, duration_ms: float | None = None,
             metadata: dict | None = None) -> "ToolResult":
        return cls(
            tool_name=tool_name, success=False, error=error, error_type=error_type,
            message=message or f"Tool '{tool_name}' failed: {error}",
            duration_ms=duration_ms, metadata=metadata or {},
        )

    def as_model_text(self) -> str:
        """What gets sent back to the model as the function response — matches
        the prior dispatcher's behavior of returning a plain result string."""
        return self.message if self.message is not None else str(self.data)
