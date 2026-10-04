"""
core.policy.config — policy configuration (Phase 6 spec, Part 11), routed
entirely through Phase 1's ConfigService — no second configuration system.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.tools.metadata import RiskLevel

_ACTION_VALUES = ("allow", "approval_required", "deny")


@dataclass(frozen=True)
class PolicyConfig:
    policy_enabled: bool = True

    default_low_risk_action: str = "allow"
    default_medium_risk_action: str = "allow"
    default_high_risk_action: str = "approval_required"
    default_critical_risk_action: str = "approval_required"

    allow_local_high_risk: bool = True
    allow_remote_high_risk: bool = True
    allow_critical_commands: bool = True

    approval_timeout_seconds: float = 120.0

    deny_remote_critical: bool = True

    def action_for(self, risk: RiskLevel) -> str:
        return {
            RiskLevel.LOW: self.default_low_risk_action,
            RiskLevel.MEDIUM: self.default_medium_risk_action,
            RiskLevel.HIGH: self.default_high_risk_action,
            RiskLevel.CRITICAL: self.default_critical_risk_action,
        }[risk]


def load_policy_config(config_service=None) -> PolicyConfig:
    if config_service is None:
        return PolicyConfig()

    def _action(key: str, default: str) -> str:
        value = config_service.get(key, default)
        return value if value in _ACTION_VALUES else default

    return PolicyConfig(
        policy_enabled=bool(config_service.get("policy_enabled", True)),
        default_low_risk_action=_action("default_low_risk_action", "allow"),
        default_medium_risk_action=_action("default_medium_risk_action", "allow"),
        default_high_risk_action=_action("default_high_risk_action", "approval_required"),
        default_critical_risk_action=_action("default_critical_risk_action", "approval_required"),
        allow_local_high_risk=bool(config_service.get("allow_local_high_risk", True)),
        allow_remote_high_risk=bool(config_service.get("allow_remote_high_risk", True)),
        allow_critical_commands=bool(config_service.get("allow_critical_commands", True)),
        approval_timeout_seconds=float(config_service.get("approval_timeout", 120.0)),
        deny_remote_critical=bool(config_service.get("deny_remote_critical", True)),
    )
