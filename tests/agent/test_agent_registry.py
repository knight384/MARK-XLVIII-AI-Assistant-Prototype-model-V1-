"""tests/agent/test_agent_registry.py"""
from __future__ import annotations

import pytest
from .conftest import EchoAgent, FailingAgent

from core.agent.base import AgentCapability
from core.agent.errors import AgentRegistrationError


def test_register_and_get(agent_registry):
    agent = EchoAgent()
    agent_registry.register(agent)
    assert agent_registry.get("echo_agent") is agent


def test_duplicate_id_raises(agent_registry):
    agent_registry.register(EchoAgent())
    with pytest.raises(AgentRegistrationError):
        agent_registry.register(EchoAgent())


def test_get_missing_returns_none(agent_registry):
    assert agent_registry.get("nonexistent") is None


def test_exists(agent_registry):
    agent_registry.register(EchoAgent())
    assert agent_registry.exists("echo_agent") is True
    assert agent_registry.exists("nonexistent") is False


def test_list_and_list_ids(agent_registry):
    agent_registry.register(EchoAgent())
    agent_registry.register(FailingAgent())
    assert len(agent_registry.list()) == 2
    assert set(agent_registry.list_ids()) == {"echo_agent", "failing_agent"}


def test_unregister(agent_registry):
    agent_registry.register(EchoAgent())
    agent_registry.unregister("echo_agent")
    assert agent_registry.get("echo_agent") is None


def test_find_by_capability(agent_registry):
    agent_registry.register(EchoAgent())
    found = agent_registry.find_by_capability(AgentCapability.RESEARCH)
    assert len(found) == 1
    assert found[0].agent_id == "echo_agent"


def test_find_by_capability_no_match(agent_registry):
    agent_registry.register(EchoAgent())
    found = agent_registry.find_by_capability(AgentCapability.CODING)
    assert found == []


def test_default_agent_registry_has_all_six_agents():
    from core.agent.registry import get_default_agent_registry
    registry = get_default_agent_registry()
    expected = {
        "developer_agent", "research_agent", "browser_agent",
        "computer_agent", "file_document_agent", "verification_agent",
    }
    assert set(registry.list_ids()) == expected


def test_no_agent_theater_each_agent_has_distinct_tool_set():
    """Spec Part 49: verify no two agents are near-identical duplicates —
    each should have a genuinely different tool set."""
    from core.agent.registry import get_default_agent_registry
    registry = get_default_agent_registry()
    tool_sets = [tuple(sorted(a.metadata.tool_names)) for a in registry.list()]
    assert len(tool_sets) == len(set(tool_sets)), "two agents have identical tool sets"
