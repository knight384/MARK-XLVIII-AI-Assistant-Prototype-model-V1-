"""
core.policy.engine — the PolicyEngine (Phase 6 spec, Part 9). The single
authorization boundary — nothing else in the codebase should implement a
second ALLOW/APPROVAL_REQUIRED/DENY decision (spec Part 5).
"""
from __future__ import annotations

import logging
import threading

from .audit import SecurityAuditEvent, emit
from .config import PolicyConfig, load_policy_config
from .models import PolicyContext, PolicyDecision, PolicyResult
from .rules import DEFAULT_RULE_CHAIN

logger = logging.getLogger(__name__)


class PolicyEngine:
    def __init__(self, config: PolicyConfig | None = None, rule_chain=None):
        self._config = config or PolicyConfig()
        self._rules = rule_chain or DEFAULT_RULE_CHAIN

    @property
    def config(self) -> PolicyConfig:
        return self._config

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        """Deterministic, rule-based (spec Part 68 — no LLM call). Fail
        closed: if a rule raises, treat as APPROVAL_REQUIRED rather than
        silently allowing (spec Part 50)."""
        try:
            for rule in self._rules:
                result = rule(ctx, self._config)
                if result is not None:
                    self._audit_evaluated(ctx, result)
                    return result
        except Exception as exc:
            logger.error("[PolicyEngine] rule evaluation raised (%s) — failing closed.", exc)
            result = PolicyResult(
                PolicyDecision.APPROVAL_REQUIRED,
                f"Policy evaluation encountered an internal error ({type(exc).__name__}); "
                f"failing closed to approval-required.",
                ctx.risk_level, matched_rule="fail_closed_error",
            )
            self._audit_evaluated(ctx, result)
            return result

        # Unreachable in practice (rule_default_risk_action always matches),
        # but if it ever happens, fail closed rather than allow.
        result = PolicyResult(PolicyDecision.APPROVAL_REQUIRED,
                               "No policy rule matched — failing closed.", ctx.risk_level,
                               matched_rule="fail_closed_no_match")
        self._audit_evaluated(ctx, result)
        return result

    def _audit_evaluated(self, ctx: PolicyContext, result: PolicyResult) -> None:
        emit(SecurityAuditEvent(
            event_type="PolicyEvaluated", request_id=ctx.request_id, task_id=ctx.task_id,
            agent_id=ctx.agent_id, tool_name=ctx.tool_name, risk_level=ctx.risk_level.value,
            decision=result.decision.value, source=ctx.source.value,
            metadata={"matched_rule": result.matched_rule},
        ))


_default_engine: PolicyEngine | None = None
_default_lock = threading.Lock()


def get_default_policy_engine() -> PolicyEngine:
    global _default_engine
    with _default_lock:
        if _default_engine is None:
            from core.config import get_config_service
            config = load_policy_config(get_config_service())
            _default_engine = PolicyEngine(config=config)
        return _default_engine
