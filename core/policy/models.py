"""
core.policy.models — provider/runtime-neutral policy models (Phase 6 spec,
Part 8).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.tools.metadata import RiskLevel


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    DENY = "DENY"


class RequestSource(str, Enum):
    """Where the tool request originated — local/remote distinction drives
    stricter defaults for remote requests (spec Part 20)."""
    LOCAL_VOICE = "local_voice"          # Gemini Live realtime session
    LOCAL_AGENT = "local_agent"          # Agent Runtime, triggered locally
    DASHBOARD = "dashboard"              # remote dashboard/web UI
    SYSTEM = "system"                    # internal/system-initiated (e.g. startup checks)
    SIDECAR = "sidecar"                  # Remote sidecar/device


@dataclass
class PolicyContext:
    """Everything the PolicyEngine needs to decide — deliberately excludes
    raw secrets and raw private memory content (spec Part 8, Part 48)."""
    tool_name: str
    risk_level: RiskLevel
    capabilities: tuple[str, ...] = ()
    agent_id: str | None = None
    agent_max_risk: RiskLevel | None = None
    task_id: str | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    source: RequestSource = RequestSource.LOCAL_AGENT
    session_id: str | None = None
    user_id: str | None = None
    involves_private_memory: bool = False
    involves_credentials: bool = False
    involves_external_communication: bool = False
    argument_summary: str = ""           # a SAFE, human-readable summary — never raw secrets
    requires_sandbox: bool = False       # set by the tool/agent when it knows execution is untrusted code
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyResult:
    decision: PolicyDecision
    reason: str
    risk_level: RiskLevel
    matched_rule: str = ""
    requires_sandbox: bool = False

    @property
    def allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW
