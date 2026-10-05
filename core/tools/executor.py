"""
core.tools.executor — the Tool Executor (Phase 3 spec, Part 18; Phase 6
spec, Part 17: PolicyEngine integration).

Flow (Phase 6):
    validate -> build PolicyContext -> PolicyEngine.evaluate()
        -> ALLOW: execute
        -> APPROVAL_REQUIRED: request approval, wait (bounded), then execute or fail
        -> DENY: fail safely, never execute

This is the single canonical execution path — every tool call, from every
agent and from the realtime voice loop, passes through here. There is no
second authorization implementation anywhere else in the codebase (spec
Part 5).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from .base import AuditHook, Tool, ToolContext, ToolEvent, default_audit_hook
from .errors import ToolNotFoundError, ToolTimeoutError
from .registry import ToolRegistry
from .results import ToolResult

logger = logging.getLogger(__name__)

_APPROVAL_POLL_INTERVAL_S = 0.25

# Heuristic-only argument redaction for policy/approval summaries (spec
# Part 22: never surface arbitrary command contents that may contain
# secrets). This mirrors core/logging_setup.py's spirit but is intentionally
# minimal/local — the goal here is a safe human-readable approval prompt,
# not a general-purpose log scrubber.
_SENSITIVE_KEY_HINTS = ("key", "token", "password", "secret", "credential", "auth")


def _summarize_args(tool_name: str, args: dict) -> str:
    parts = []
    for k, v in (args or {}).items():
        if any(hint in k.lower() for hint in _SENSITIVE_KEY_HINTS):
            parts.append(f"{k}=***REDACTED***")
            continue
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s}")
    return f"{tool_name}(" + ", ".join(parts) + ")"


@dataclass
class _ApprovalOutcome:
    ok: bool
    reason: str = ""
    error_type: str = ""
    approval_id: str | None = None


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, audit_hook: AuditHook | None = None,
                 policy_engine=None, approval_manager=None):
        self._registry = registry
        self._audit_hook = audit_hook or default_audit_hook
        self._policy_engine = policy_engine
        self._approval_manager = approval_manager

    def _get_policy_engine(self):
        if self._policy_engine is None:
            from core.policy import get_default_policy_engine
            self._policy_engine = get_default_policy_engine()
        return self._policy_engine

    def _get_approval_manager(self):
        if self._approval_manager is None:
            from core.policy import get_default_approval_manager
            self._approval_manager = get_default_approval_manager()
        return self._approval_manager

    async def execute(self, tool_name: str, args: dict, context: ToolContext) -> ToolResult:
        t0 = time.perf_counter()
        tool = self._registry.get(tool_name)

        if tool is None:
            err = ToolNotFoundError(f"Unknown tool: {tool_name}", tool_name=tool_name)
            self._emit(ToolEvent(type="failed", tool_name=tool_name, request_id=context.request_id,
                                  detail=str(err)))
            return ToolResult.fail(tool_name, error=str(err), error_type="ToolNotFoundError")

        # 1. Validate input (Phase 3 Part 19) — structured failure, not a crash.
        validation_errors = tool.schema.validate(args)
        if validation_errors:
            detail = "; ".join(validation_errors)
            self._emit(ToolEvent(type="failed", tool_name=tool_name, request_id=context.request_id,
                                  detail=f"validation: {detail}"))
            return ToolResult.fail(tool_name, error=detail, error_type="ToolValidationError",
                                    message=f"Invalid arguments for '{tool_name}': {detail}")

        # 2. Policy evaluation (Phase 6) — the single authorization boundary.
        from core.policy import PolicyDecision
        from core.policy.audit import SecurityAuditEvent, emit as audit_emit

        action_summary = _summarize_args(tool_name, args)
        policy_result = self._evaluate_policy(tool, args, context)

        if policy_result.decision == PolicyDecision.DENY:
            audit_emit(SecurityAuditEvent(
                event_type="ToolDenied", request_id=context.request_id, task_id=context.task_id,
                agent_id=context.agent_id, tool_name=tool_name, risk_level=tool.metadata.risk_level.value,
                decision="DENY", source=context.source, result_status="denied",
                metadata={"reason": policy_result.reason},
            ))
            return ToolResult.fail(
                tool_name, error=policy_result.reason, error_type="PolicyDeniedError",
                message=f"'{tool_name}' was denied by policy: {policy_result.reason}",
            )

        if policy_result.decision == PolicyDecision.APPROVAL_REQUIRED:
            outcome = await self._resolve_approval(tool, action_summary, context)
            if not outcome.ok:
                audit_emit(SecurityAuditEvent(
                    event_type="ApprovalDenied", request_id=context.request_id, task_id=context.task_id,
                    agent_id=context.agent_id, tool_name=tool_name, risk_level=tool.metadata.risk_level.value,
                    decision="APPROVAL_REQUIRED", source=context.source, result_status="denied",
                    metadata={"reason": outcome.reason},
                ))
                return ToolResult.fail(
                    tool_name, error=outcome.reason, error_type=outcome.error_type or "ApprovalDeniedError",
                    message=f"'{tool_name}' requires approval: {outcome.reason}",
                    metadata={"approval_id": outcome.approval_id, "policy_decision": "APPROVAL_REQUIRED"},
                )
            audit_emit(SecurityAuditEvent(
                event_type="ApprovalGranted", request_id=context.request_id, task_id=context.task_id,
                agent_id=context.agent_id, tool_name=tool_name, risk_level=tool.metadata.risk_level.value,
                decision="ALLOW", source=context.source, result_status="approved",
            ))

        audit_emit(SecurityAuditEvent(
            event_type="ToolAllowed", request_id=context.request_id, task_id=context.task_id,
            agent_id=context.agent_id, tool_name=tool_name, risk_level=tool.metadata.risk_level.value,
            decision="ALLOW", source=context.source,
        ))

        # 3. Execute (unchanged from Phase 3, plus audit calls).
        self._emit(ToolEvent(type="started", tool_name=tool_name, request_id=context.request_id))

        try:
            timeout = tool.metadata.timeout_seconds
            coro = tool.execute(args, context)
            result = await asyncio.wait_for(coro, timeout=timeout) if timeout else await coro
        except asyncio.TimeoutError as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            err = ToolTimeoutError(f"Tool '{tool_name}' timed out after {tool.metadata.timeout_seconds}s",
                                    tool_name=tool_name, cause=exc)
            logger.error(str(err))
            self._emit(ToolEvent(type="failed", tool_name=tool_name, request_id=context.request_id,
                                  detail="timeout"))
            audit_emit(SecurityAuditEvent(
                event_type="ToolExecuted", request_id=context.request_id, task_id=context.task_id,
                agent_id=context.agent_id, tool_name=tool_name, risk_level=tool.metadata.risk_level.value,
                decision="ALLOW", source=context.source, duration_ms=duration_ms, result_status="timeout",
            ))
            return ToolResult.fail(tool_name, error=str(err), error_type="ToolTimeoutError",
                                    duration_ms=duration_ms)
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.exception("Tool '%s' raised an unhandled exception.", tool_name)
            self._emit(ToolEvent(type="failed", tool_name=tool_name, request_id=context.request_id,
                                  detail=f"{type(exc).__name__}: {exc}"))
            audit_emit(SecurityAuditEvent(
                event_type="ToolExecuted", request_id=context.request_id, task_id=context.task_id,
                agent_id=context.agent_id, tool_name=tool_name, risk_level=tool.metadata.risk_level.value,
                decision="ALLOW", source=context.source, duration_ms=duration_ms, result_status="failed",
            ))
            return ToolResult.fail(
                tool_name, error=str(exc), error_type=type(exc).__name__,
                message=f"Tool '{tool_name}' failed: {exc}", duration_ms=duration_ms,
            )

        duration_ms = (time.perf_counter() - t0) * 1000
        if result.duration_ms is None:
            result.duration_ms = duration_ms

        if tool.metadata.supports_verification:
            try:
                verification = await tool.verify(result, context)
                if verification is not None:
                    result.metadata["verification"] = {
                        "verified": verification.verified, "detail": verification.detail,
                    }
            except Exception as exc:
                logger.warning("Verification hook raised for tool '%s': %s", tool_name, exc)

        self._emit(ToolEvent(
            type="completed" if result.success else "failed",
            tool_name=tool_name, request_id=context.request_id,
            detail=result.error or "",
        ))
        audit_emit(SecurityAuditEvent(
            event_type="ToolExecuted", request_id=context.request_id, task_id=context.task_id,
            agent_id=context.agent_id, tool_name=tool_name, risk_level=tool.metadata.risk_level.value,
            decision="ALLOW", source=context.source, duration_ms=duration_ms,
            result_status="completed" if result.success else "failed",
        ))
        return result

    def _evaluate_policy(self, tool: Tool, args: dict, context: ToolContext):
        from core.policy import PolicyContext, RequestSource
        try:
            if context.source and context.source.startswith("sidecar_"):
                source = RequestSource.SIDECAR
            else:
                source = RequestSource(context.source)
        except ValueError:
            source = RequestSource.LOCAL_AGENT

        metadata = {}
        if tool.metadata.requires_sandbox:
            # Probe SandboxManager so rule_sandbox_required_unavailable can
            # fail closed instead of silently falling back to an
            # unsandboxed host run (spec Part 25/50).
            from core.sandbox import get_default_sandbox_manager
            manager = get_default_sandbox_manager()
            backend = manager.select_backend(tool.metadata.risk_level)
            metadata["sandbox_available"] = backend is not None

        ctx = PolicyContext(
            tool_name=tool.name, risk_level=tool.metadata.risk_level,
            capabilities=tuple(c.value for c in tool.metadata.capabilities),
            agent_id=context.agent_id, agent_max_risk=context.agent_max_risk,
            task_id=context.task_id, request_id=context.request_id,
            source=source, session_id=context.session_id,
            argument_summary=_summarize_args(tool.name, args),
            requires_sandbox=tool.metadata.requires_sandbox,
            metadata=metadata,
        )
        return self._get_policy_engine().evaluate(ctx)

    async def _resolve_approval(self, tool: Tool, action_summary: str, context: ToolContext) -> _ApprovalOutcome:
        """If context.approval_id is already set (caller re-submitting
        after obtaining approval out-of-band), validates and consumes it
        immediately. Otherwise creates a new approval request and waits
        (bounded by the policy's approval_timeout_seconds) for resolution."""
        from core.policy import (
            ApprovalDeniedError, ApprovalMismatchError, ApprovalNotFoundError,
            ApprovalTimeoutError, RequestSource,
        )
        from core.policy.approval import ApprovalStatus

        manager = self._get_approval_manager()

        if context.approval_id:
            try:
                manager.check_and_consume(context.approval_id, tool.name, action_summary, context.session_id)
                return _ApprovalOutcome(True, approval_id=context.approval_id)
            except (ApprovalDeniedError, ApprovalTimeoutError, ApprovalMismatchError, ApprovalNotFoundError) as exc:
                return _ApprovalOutcome(False, str(exc), type(exc).__name__, context.approval_id)

        try:
            if context.source and context.source.startswith("sidecar_"):
                source = RequestSource.SIDECAR
            else:
                source = RequestSource(context.source)
        except ValueError:
            source = RequestSource.LOCAL_AGENT

        engine = self._get_policy_engine()
        timeout = engine.config.approval_timeout_seconds
        req = manager.request(
            tool.name, action_summary, tool.metadata.risk_level,
            agent=context.agent_id, task=context.task_id, source=source,
            session_id=context.session_id, timeout_seconds=timeout,
        )

        from core.policy.audit import SecurityAuditEvent, emit as audit_emit
        audit_emit(SecurityAuditEvent(
            event_type="ApprovalRequested", request_id=context.request_id, task_id=context.task_id,
            agent_id=context.agent_id, tool_name=tool.name, risk_level=tool.metadata.risk_level.value,
            decision="APPROVAL_REQUIRED", source=context.source,
            metadata={"approval_id": req.approval_id},
        ))

        elapsed = 0.0
        while elapsed < timeout:
            current = manager.get(req.approval_id)
            if current is None:
                return _ApprovalOutcome(False, "Approval request vanished unexpectedly.", "ApprovalNotFoundError")
            if current.status == ApprovalStatus.APPROVED:
                try:
                    manager.check_and_consume(req.approval_id, tool.name, action_summary, context.session_id)
                    return _ApprovalOutcome(True, approval_id=req.approval_id)
                except Exception as exc:
                    return _ApprovalOutcome(False, str(exc), type(exc).__name__, req.approval_id)
            if current.status in (ApprovalStatus.DENIED, ApprovalStatus.CANCELLED, ApprovalStatus.EXPIRED):
                return _ApprovalOutcome(False, current.resolution_reason or current.status.value,
                                         "ApprovalDeniedError", req.approval_id)
            if context.cancellation_token is not None and context.cancellation_token.is_cancelled:
                manager.cancel(req.approval_id)
                return _ApprovalOutcome(False, "Cancelled while awaiting approval.",
                                         "ToolCancelledError", req.approval_id)
            await asyncio.sleep(_APPROVAL_POLL_INTERVAL_S)
            elapsed += _APPROVAL_POLL_INTERVAL_S

        manager.expire_stale()
        return _ApprovalOutcome(False, f"Approval request timed out after {timeout}s.",
                                 "ApprovalTimeoutError", req.approval_id)

    def _emit(self, event: ToolEvent) -> None:
        try:
            self._audit_hook(event)
        except Exception:
            logger.warning("Audit hook raised for event %s/%s", event.type, event.tool_name)
