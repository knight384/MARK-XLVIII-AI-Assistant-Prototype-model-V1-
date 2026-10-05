"""
core.policy.rules — deterministic policy rules (Phase 6 spec, Parts 9-10,
19-20, 50-51). No LLM call is used to decide ALLOW/APPROVAL_REQUIRED/DENY
(spec Part 68) — every rule here is a plain, explainable Python function.

Rules are evaluated in priority order by PolicyEngine; the first rule that
returns a non-None PolicyResult wins. Order matters: fail-closed checks and
agent-risk-limit enforcement run before the general risk-level default, so
they can only make the decision stricter, never looser.
"""
from __future__ import annotations

from core.tools.metadata import RiskLevel

from .config import PolicyConfig
from .models import PolicyContext, PolicyDecision, PolicyResult, RequestSource

_RISK_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}


def rule_policy_disabled(ctx: PolicyContext, config: PolicyConfig) -> PolicyResult | None:
    """spec Part 38-style disabled mode, but for policy: if policy is
    disabled, LOW/MEDIUM degrade to ALLOW (informational tools keep
    working), but HIGH/CRITICAL still fail closed (spec Part 50: 'Low-risk
    informational tools may degrade gracefully' — dangerous ones must not)."""
    if config.policy_enabled:
        return None
    if _RISK_ORDER[ctx.risk_level] <= _RISK_ORDER[RiskLevel.MEDIUM]:
        return PolicyResult(PolicyDecision.ALLOW, "Policy disabled; low/medium risk degrades to allow.",
                             ctx.risk_level, matched_rule="policy_disabled")
    return PolicyResult(PolicyDecision.APPROVAL_REQUIRED,
                         "Policy engine is disabled, but high/critical-risk actions still require "
                         "approval as a fail-closed safeguard.", ctx.risk_level,
                         matched_rule="policy_disabled_fail_closed")


def rule_agent_risk_limit(ctx: PolicyContext, config: PolicyConfig) -> PolicyResult | None:
    """spec Part 19: an agent must never silently exceed its declared
    max_declared_risk. If the tool's risk exceeds what the calling agent is
    allowed to request, deny outright — no approval path elevates an
    agent's own ceiling (spec Part 51: 'No silent escalation')."""
    if ctx.agent_id is None or ctx.agent_max_risk is None:
        return None
    if _RISK_ORDER[ctx.risk_level] > _RISK_ORDER[ctx.agent_max_risk]:
        return PolicyResult(
            PolicyDecision.DENY,
            f"Agent '{ctx.agent_id}' has max_declared_risk={ctx.agent_max_risk.value}, "
            f"but tool '{ctx.tool_name}' is {ctx.risk_level.value}. Denied — an agent cannot "
            f"exceed its declared risk ceiling.",
            ctx.risk_level, matched_rule="agent_risk_limit",
        )
    return None


def rule_critical_commands_disabled(ctx: PolicyContext, config: PolicyConfig) -> PolicyResult | None:
    if ctx.risk_level == RiskLevel.CRITICAL and not config.allow_critical_commands:
        return PolicyResult(PolicyDecision.DENY,
                             "CRITICAL-risk commands are disabled by policy configuration.",
                             ctx.risk_level, matched_rule="critical_commands_disabled")
    return None


def rule_remote_critical(ctx: PolicyContext, config: PolicyConfig) -> PolicyResult | None:
    """spec Part 20: 'Remote CRITICAL -> DENY by default.'"""
    if ctx.source in (RequestSource.DASHBOARD, RequestSource.SIDECAR) and ctx.risk_level == RiskLevel.CRITICAL and config.deny_remote_critical:
        return PolicyResult(PolicyDecision.DENY,
                             "CRITICAL-risk actions are not permitted from remote/dashboard/sidecar sessions.",
                             ctx.risk_level, matched_rule="remote_critical_denied")
    return None


def rule_remote_high_disabled(ctx: PolicyContext, config: PolicyConfig) -> PolicyResult | None:
    if (ctx.source in (RequestSource.DASHBOARD, RequestSource.SIDECAR) and ctx.risk_level == RiskLevel.HIGH
            and not config.allow_remote_high_risk):
        return PolicyResult(PolicyDecision.DENY,
                             "HIGH-risk actions from remote/dashboard/sidecar sessions are disabled by policy.",
                             ctx.risk_level, matched_rule="remote_high_disabled")
    return None


def rule_local_high_disabled(ctx: PolicyContext, config: PolicyConfig) -> PolicyResult | None:
    if (ctx.source in (RequestSource.LOCAL_VOICE, RequestSource.LOCAL_AGENT)
            and ctx.risk_level == RiskLevel.HIGH and not config.allow_local_high_risk):
        return PolicyResult(PolicyDecision.APPROVAL_REQUIRED,
                             "HIGH-risk local actions require approval (allow_local_high_risk is disabled).",
                             ctx.risk_level, matched_rule="local_high_disabled")
    return None


def rule_sandbox_required_unavailable(ctx: PolicyContext, config: PolicyConfig) -> PolicyResult | None:
    """spec Part 25/59: if the tool has flagged that it needs a sandbox for
    this specific call (untrusted/model-generated code) and none is
    available, fail closed rather than silently running on the host. This
    rule only fires when the caller has already determined sandbox
    unavailability and set ctx.metadata['sandbox_available'] = False —
    the PolicyEngine itself doesn't probe Docker (that's SandboxManager's
    job); this rule just makes the fail-closed consequence explicit."""
    if ctx.requires_sandbox and ctx.metadata.get("sandbox_available") is False:
        return PolicyResult(
            PolicyDecision.DENY,
            f"'{ctx.tool_name}' requires isolated execution and no sandbox is currently available "
            f"on this system. Refusing to execute unsandboxed for safety.",
            ctx.risk_level, matched_rule="sandbox_required_unavailable",
        )
    return None


def rule_default_risk_action(ctx: PolicyContext, config: PolicyConfig) -> PolicyResult | None:
    """The baseline default policy (spec Part 10) — always matches if
    nothing stricter fired first, so this is intentionally last."""
    action = config.action_for(ctx.risk_level)
    decision = {
        "allow": PolicyDecision.ALLOW,
        "approval_required": PolicyDecision.APPROVAL_REQUIRED,
        "deny": PolicyDecision.DENY,
    }[action]
    reason = {
        PolicyDecision.ALLOW: f"{ctx.risk_level.value}-risk actions are allowed by default policy.",
        PolicyDecision.APPROVAL_REQUIRED: f"{ctx.risk_level.value}-risk actions require approval by default policy.",
        PolicyDecision.DENY: f"{ctx.risk_level.value}-risk actions are denied by default policy.",
    }[decision]
    return PolicyResult(decision, reason, ctx.risk_level, matched_rule="default_risk_action",
                         requires_sandbox=ctx.requires_sandbox)


# Priority order: fail-closed / hard limits first, general default last.
# agent_risk_limit runs before policy_disabled so an agent's risk ceiling
# is enforced even when the general policy is administratively disabled
# (spec Part 51: no silent escalation, ever, under any configuration).
DEFAULT_RULE_CHAIN = (
    rule_agent_risk_limit,
    rule_policy_disabled,
    rule_critical_commands_disabled,
    rule_remote_critical,
    rule_remote_high_disabled,
    rule_local_high_disabled,
    rule_sandbox_required_unavailable,
    rule_default_risk_action,
)
