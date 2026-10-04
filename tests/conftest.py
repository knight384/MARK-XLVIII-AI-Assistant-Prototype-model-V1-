"""
tests/conftest.py — shared fixtures for the Phase 1 foundation test suite.

Two things every test here needs isolation from:
  1. The ConfigService singleton (module-level state) -- reset between tests
     so one test's writes don't leak into another's assertions.
  2. The real config/ directory on disk -- tests point ConfigService at a
     temp directory instead, so running the suite never touches (or risks
     corrupting) a real config/api_keys.json / secrets.json on a developer's
     machine.
"""
import sys
from pathlib import Path

import pytest

# Ensure the project root (the "MARK XLVIII" folder) is importable as the
# top-level package root, matching how main.py imports `core.config` etc.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config.service import ConfigService  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_config_singleton():
    """Reset the ConfigService singleton before and after every test so
    tests don't observe each other's state."""
    ConfigService._instance = None
    yield
    ConfigService._instance = None


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """A ConfigService instance rooted at a throwaway temp directory."""
    monkeypatch.setattr(
        "core.config.service._get_base_dir", lambda: tmp_path
    )
    ConfigService._instance = None
    return ConfigService()


@pytest.fixture(autouse=True)
def _reset_policy_singletons():
    """Phase 6: reset the PolicyEngine/ApprovalManager singletons before and
    after every test, and default the engine to a permissive ("allow"
    every risk level) configuration.

    Rationale: tests written before Phase 6 (Phase 3/4/5's tool/agent
    tests) construct a plain `ToolExecutor(registry)` and expect it to run
    a tool directly — that is still exactly what happens under an
    allow-all policy. Without this fixture, those same tests would hit
    Phase 6's new default policy (HIGH/CRITICAL -> APPROVAL_REQUIRED) and
    hang waiting for an approval that will never come, up to the full
    approval_timeout_seconds, for every HIGH/CRITICAL-risk production tool
    exercised in tests/tools/test_production_tools.py.

    Tests that specifically exercise policy behavior (tests/policy/) build
    their own explicit PolicyEngine/PolicyConfig and pass it to
    ToolExecutor directly, which overrides this default."""
    import core.policy.engine as engine_module
    import core.policy.approval as approval_module
    from core.policy.config import PolicyConfig
    from core.policy.engine import PolicyEngine

    engine_module._default_engine = PolicyEngine(config=PolicyConfig(
        default_low_risk_action="allow", default_medium_risk_action="allow",
        default_high_risk_action="allow", default_critical_risk_action="allow",
    ))
    approval_module._default_manager = None
    yield
    engine_module._default_engine = None
    approval_module._default_manager = None
