"""
core.policy.audit — formalized security audit events (Phase 6 spec, Parts
21-22). Uses Phase 1's structured logging only — no durable audit database
yet (a future phase may add one; the event shape here is already
serializable and ready for that).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jarvis.audit")

_EVENT_TYPES = (
    "PolicyEvaluated", "ApprovalRequested", "ApprovalGranted", "ApprovalDenied",
    "ToolAllowed", "ToolDenied", "ToolExecuted",
    "SandboxStarted", "SandboxCompleted", "SandboxFailed",
)


@dataclass
class SecurityAuditEvent:
    event_type: str
    request_id: str = ""
    task_id: str | None = None
    agent_id: str | None = None
    tool_name: str = ""
    risk_level: str = ""
    decision: str = ""
    source: str = ""
    duration_ms: float | None = None
    result_status: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.event_type not in _EVENT_TYPES:
            raise ValueError(f"Unknown audit event type: {self.event_type}")


def emit(event: SecurityAuditEvent) -> None:
    """Never logs secrets/passwords/tokens/private memory/raw command
    content that may contain secrets (spec Part 22) — only the safe,
    structured fields on SecurityAuditEvent itself. Callers are responsible
    for keeping `metadata` free of anything sensitive; this function does
    not additionally sanitize free-form metadata content."""
    level = logging.WARNING if event.decision == "DENY" or event.result_status == "failed" else logging.INFO
    logger.log(
        level,
        "[Audit] %s tool=%s risk=%s decision=%s source=%s agent=%s task=%s request=%s "
        "duration_ms=%s status=%s",
        event.event_type, event.tool_name, event.risk_level, event.decision, event.source,
        event.agent_id, event.task_id, event.request_id, event.duration_ms, event.result_status,
    )
