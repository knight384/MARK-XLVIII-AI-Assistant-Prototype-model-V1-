"""
core.tools.base — the standard Tool interface (Phase 3 spec, Part 7),
ToolContext (Part 11), and CancellationToken (Part 21).
"""
from __future__ import annotations

import logging
import threading
import uuid
from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .metadata import ToolMetadata
from .results import ToolResult
from .schemas import ToolSchema

class CancelReason(str, Enum):
    USER_REQUEST = "user_request"
    TIMEOUT = "timeout"
    DISCONNECT = "disconnect"
    SYSTEM_SHUTDOWN = "system_shutdown"


logger = logging.getLogger(__name__)


class CancellationToken:
    """A simple cooperative cancellation flag. Tools that support
    cancellation should poll `is_cancelled` at safe points; nothing here
    forcibly interrupts a running OS-automation call, since that could leave
    partially-completed operations (spec Part 20: 'Do not blindly wrap
    synchronous OS automation in cancellation logic that can leave partially
    completed operations.')."""

    def __init__(self):
        self._event = threading.Event()
        self._reason: Optional[CancelReason] = None

    def cancel(self, reason: CancelReason = CancelReason.USER_REQUEST) -> None:
        self._reason = reason
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()
        
    @property
    def reason(self) -> Optional[CancelReason]:
        return self._reason


@dataclass
class ToolContext:
    """Execution context passed to every tool. Deliberately loose/optional
    on most fields (spec Part 11: 'prevent tools from depending directly on
    global runtime state', but Mission/task/user systems don't exist yet).

    `extra` is an explicit escape hatch for the small number of tools that
    still need direct access to live JARVIS runtime state (the PyQt UI
    handle, the speak() callback, in-session vision cooldown state) to
    preserve their exact existing behavior without inventing new
    abstractions for state that Phase 4/5 will formalize properly. Standard
    tools should not need to touch `extra` at all.
    """
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_id: str | None = None
    user_id: str | None = None
    config: Any = None                          # normally core.config.ConfigService
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)
    logger: logging.Logger = field(default_factory=lambda: logger)
    extra: dict[str, Any] = field(default_factory=dict)

    # Phase 6: policy-relevant context. Kept as plain strings/optionals so
    # core/tools/ doesn't take a hard import-time dependency on
    # core/policy/ — ToolExecutor converts these into a real PolicyContext
    # at evaluation time.
    agent_id: str | None = None
    agent_max_risk: Any = None            # core.tools.metadata.RiskLevel | None
    source: str = "local_agent"           # "local_voice" | "local_agent" | "dashboard" | "system"
    session_id: str | None = None
    approval_id: str | None = None        # set by a caller re-submitting after obtaining approval


class Tool(ABC):
    """Standard tool abstraction. Concrete tools either wrap an existing
    actions/*.py function (the common case) or implement bespoke logic for
    JARVIS-runtime-coupled behavior (save_memory, screen_process, etc.) —
    see core/tools/definitions.py for both patterns."""

    name: str
    description: str
    schema: ToolSchema
    metadata: ToolMetadata

    @abstractmethod
    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        """Must return a ToolResult, never raise for expected/handled
        failures — only let genuinely unexpected exceptions propagate (the
        Executor will catch and normalize those too, but a well-behaved tool
        catches its own known failure modes)."""
        raise NotImplementedError

    async def verify(self, result: ToolResult, context: ToolContext) -> "VerificationResult | None":
        """Optional verification hook (spec Part 22). Returning None means
        'this tool doesn't support verification' — the Executor treats that
        as a no-op, not a failure."""
        return None

    def gemini_declaration(self) -> dict:
        return self.schema.to_gemini_declaration(self.name, self.description)


@dataclass
class VerificationResult:
    verified: bool
    detail: str = ""


# -- audit hook events (Phase 3 spec, Part 23) -------------------------

@dataclass
class ToolEvent:
    type: str          # "started" | "completed" | "failed" | "cancelled"
    tool_name: str
    request_id: str
    detail: str = ""


AuditHook = Callable[[ToolEvent], None]


def default_audit_hook(event: ToolEvent) -> None:
    """Uses Phase 1's logging infrastructure only — no durable audit
    database yet (that's Phase 6)."""
    level = logging.WARNING if event.type == "failed" else logging.INFO
    logger.log(level, "[ToolAudit] %s %s (request_id=%s) %s",
               event.type, event.tool_name, event.request_id, event.detail)
