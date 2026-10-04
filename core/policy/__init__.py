"""
core.policy — the Policy Engine and Approval workflow (Phase 6).

Typical usage (from ToolExecutor, see core/tools/executor.py):

    from core.policy import get_default_policy_engine, PolicyContext, PolicyDecision

    engine = get_default_policy_engine()
    ctx = PolicyContext(tool_name=tool.name, risk_level=tool.metadata.risk_level, ...)
    result = engine.evaluate(ctx)
    if result.decision == PolicyDecision.DENY:
        ...
    elif result.decision == PolicyDecision.APPROVAL_REQUIRED:
        ...
"""
from .approval import ApprovalManager, ApprovalRequest, ApprovalStatus, get_default_approval_manager
from .audit import SecurityAuditEvent, emit
from .config import PolicyConfig, load_policy_config
from .engine import PolicyEngine, get_default_policy_engine
from .errors import (
    ApprovalDeniedError, ApprovalMismatchError, ApprovalNotFoundError, ApprovalTimeoutError,
    PolicyDeniedError, PolicyError,
)
from .models import PolicyContext, PolicyDecision, PolicyResult, RequestSource

__all__ = [
    "PolicyEngine", "get_default_policy_engine",
    "PolicyContext", "PolicyDecision", "PolicyResult", "RequestSource",
    "PolicyConfig", "load_policy_config",
    "ApprovalManager", "ApprovalRequest", "ApprovalStatus", "get_default_approval_manager",
    "SecurityAuditEvent", "emit",
    "PolicyError", "PolicyDeniedError", "ApprovalTimeoutError", "ApprovalDeniedError",
    "ApprovalNotFoundError", "ApprovalMismatchError",
]
