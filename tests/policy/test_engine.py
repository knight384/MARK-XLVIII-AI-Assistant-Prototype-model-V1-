"""tests/policy/test_engine.py"""
from __future__ import annotations

from core.policy.config import PolicyConfig
from core.policy.engine import PolicyEngine
from core.policy.models import PolicyContext, PolicyDecision, RequestSource
from core.tools.metadata import RiskLevel


def _ctx(**kwargs) -> PolicyContext:
    defaults = dict(tool_name="test_tool", risk_level=RiskLevel.LOW)
    defaults.update(kwargs)
    return PolicyContext(**defaults)


def test_low_risk_allowed_by_default():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.LOW))
    assert result.decision == PolicyDecision.ALLOW


def test_medium_risk_allowed_by_default():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.MEDIUM))
    assert result.decision == PolicyDecision.ALLOW


def test_high_risk_requires_approval_by_default():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.HIGH))
    assert result.decision == PolicyDecision.APPROVAL_REQUIRED


def test_critical_risk_requires_approval_by_default():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.CRITICAL))
    assert result.decision == PolicyDecision.APPROVAL_REQUIRED


def test_critical_denied_when_disabled_by_config():
    engine = PolicyEngine(config=PolicyConfig(allow_critical_commands=False))
    result = engine.evaluate(_ctx(risk_level=RiskLevel.CRITICAL))
    assert result.decision == PolicyDecision.DENY


def test_configurable_medium_action():
    engine = PolicyEngine(config=PolicyConfig(default_medium_risk_action="approval_required"))
    result = engine.evaluate(_ctx(risk_level=RiskLevel.MEDIUM))
    assert result.decision == PolicyDecision.APPROVAL_REQUIRED


# -- agent risk limit enforcement (spec Part 19) --------------------------

def test_agent_within_risk_limit_uses_default_action():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.LOW, agent_id="research_agent",
                                    agent_max_risk=RiskLevel.LOW))
    assert result.decision == PolicyDecision.ALLOW


def test_agent_exceeding_risk_limit_is_denied():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.CRITICAL, agent_id="research_agent",
                                    agent_max_risk=RiskLevel.LOW))
    assert result.decision == PolicyDecision.DENY
    assert "research_agent" in result.reason


def test_agent_at_exact_risk_limit_is_not_denied():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.HIGH, agent_id="dev_agent_x",
                                    agent_max_risk=RiskLevel.HIGH))
    assert result.decision != PolicyDecision.DENY


def test_agent_risk_limit_cannot_be_bypassed_by_disabling_policy():
    """spec Part 51: no silent escalation, ever."""
    engine = PolicyEngine(config=PolicyConfig(policy_enabled=False))
    result = engine.evaluate(_ctx(risk_level=RiskLevel.CRITICAL, agent_id="x", agent_max_risk=RiskLevel.LOW))
    assert result.decision == PolicyDecision.DENY


# -- local vs remote (spec Part 20) ----------------------------------------

def test_remote_critical_denied_by_default():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.CRITICAL, source=RequestSource.DASHBOARD))
    assert result.decision == PolicyDecision.DENY


def test_local_critical_not_auto_denied():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.CRITICAL, source=RequestSource.LOCAL_AGENT))
    assert result.decision == PolicyDecision.APPROVAL_REQUIRED  # not DENY


def test_remote_critical_can_be_enabled_via_config():
    engine = PolicyEngine(config=PolicyConfig(deny_remote_critical=False))
    result = engine.evaluate(_ctx(risk_level=RiskLevel.CRITICAL, source=RequestSource.DASHBOARD))
    assert result.decision != PolicyDecision.DENY


def test_remote_high_can_be_disabled_via_config():
    engine = PolicyEngine(config=PolicyConfig(allow_remote_high_risk=False))
    result = engine.evaluate(_ctx(risk_level=RiskLevel.HIGH, source=RequestSource.DASHBOARD))
    assert result.decision == PolicyDecision.DENY


def test_local_high_disabled_requires_approval_not_deny():
    engine = PolicyEngine(config=PolicyConfig(allow_local_high_risk=False))
    result = engine.evaluate(_ctx(risk_level=RiskLevel.HIGH, source=RequestSource.LOCAL_AGENT))
    assert result.decision == PolicyDecision.APPROVAL_REQUIRED


# -- disabled policy / fail-closed (spec Part 50) --------------------------

def test_disabled_policy_low_risk_degrades_to_allow():
    engine = PolicyEngine(config=PolicyConfig(policy_enabled=False))
    result = engine.evaluate(_ctx(risk_level=RiskLevel.LOW))
    assert result.decision == PolicyDecision.ALLOW


def test_disabled_policy_high_risk_still_fails_closed():
    engine = PolicyEngine(config=PolicyConfig(policy_enabled=False))
    result = engine.evaluate(_ctx(risk_level=RiskLevel.HIGH))
    assert result.decision == PolicyDecision.APPROVAL_REQUIRED


def test_malformed_rule_fails_closed_not_open():
    def broken_rule(ctx, config):
        raise RuntimeError("simulated policy service failure")

    engine = PolicyEngine(rule_chain=(broken_rule,))
    result = engine.evaluate(_ctx(risk_level=RiskLevel.LOW))
    assert result.decision == PolicyDecision.APPROVAL_REQUIRED  # never silently ALLOW on error


def test_sandbox_required_and_unavailable_denies():
    engine = PolicyEngine()
    ctx = _ctx(risk_level=RiskLevel.HIGH, requires_sandbox=True, metadata={"sandbox_available": False})
    result = engine.evaluate(ctx)
    assert result.decision == PolicyDecision.DENY


def test_sandbox_required_and_available_proceeds_normally():
    engine = PolicyEngine()
    ctx = _ctx(risk_level=RiskLevel.LOW, requires_sandbox=True, metadata={"sandbox_available": True})
    result = engine.evaluate(ctx)
    assert result.decision == PolicyDecision.ALLOW


# -- explainability (spec Part 49) -----------------------------------------

def test_deny_reason_is_human_readable():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.CRITICAL, source=RequestSource.DASHBOARD))
    assert isinstance(result.reason, str) and len(result.reason) > 10


def test_result_has_matched_rule_name():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx(risk_level=RiskLevel.LOW))
    assert result.matched_rule
