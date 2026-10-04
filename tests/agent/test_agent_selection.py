"""
tests/agent/test_agent_selection.py — confirms the capability -> agent
mapping specified in the Phase 4 spec's Part 13 example table, using the
REAL default agent registry (not fakes) since this is specifically testing
the production agent definitions.
"""
from __future__ import annotations

from core.agent.base import AgentCapability
from core.agent.registry import get_default_agent_registry


def _first_match(capability: AgentCapability) -> str:
    registry = get_default_agent_registry()
    matches = registry.find_by_capability(capability)
    assert matches, f"no agent declares capability {capability}"
    return matches[0].agent_id


def test_coding_task_routes_to_developer_agent():
    assert _first_match(AgentCapability.CODING) == "developer_agent"


def test_research_task_routes_to_research_agent():
    assert _first_match(AgentCapability.RESEARCH) == "research_agent"


def test_browser_task_routes_to_browser_agent():
    assert _first_match(AgentCapability.BROWSER_AUTOMATION) == "browser_agent"


def test_computer_task_routes_to_computer_agent():
    assert _first_match(AgentCapability.COMPUTER_CONTROL) == "computer_agent"


def test_document_task_routes_to_file_document_agent():
    assert _first_match(AgentCapability.DOCUMENT_INTELLIGENCE) == "file_document_agent"
    assert _first_match(AgentCapability.FILE_MANAGEMENT) == "file_document_agent"


def test_verification_task_routes_to_verification_agent():
    assert _first_match(AgentCapability.VERIFICATION) == "verification_agent"


def test_every_agent_tool_name_is_actually_registered_in_tool_registry():
    """Cross-check: every tool name an agent declares must exist in the
    real Tool Registry — an agent referencing a nonexistent tool would be
    a silent Phase 3/4 integration bug."""
    from core.tools.registry import get_default_registry as get_default_tool_registry
    tool_registry = get_default_tool_registry()
    agent_registry = get_default_agent_registry()

    for agent in agent_registry.list():
        for tool_name in agent.metadata.tool_names:
            assert tool_registry.exists(tool_name), (
                f"{agent.agent_id} declares tool '{tool_name}' which is not registered "
                f"in the Tool Registry"
            )


def test_agent_max_declared_risk_matches_its_riskiest_tool():
    """Sanity check: an agent's max_declared_risk should be >= the highest
    risk_level among its own declared tools — catches metadata drift if a
    tool's risk is bumped later without updating the agent."""
    from core.tools.metadata import RiskLevel
    from core.tools.registry import get_default_registry as get_default_tool_registry

    order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
    tool_registry = get_default_tool_registry()
    agent_registry = get_default_agent_registry()

    for agent in agent_registry.list():
        highest = RiskLevel.LOW
        for tool_name in agent.metadata.tool_names:
            tool = tool_registry.get(tool_name)
            if tool and order[tool.metadata.risk_level] > order[highest]:
                highest = tool.metadata.risk_level
        assert order[agent.metadata.max_declared_risk] >= order[highest], (
            f"{agent.agent_id} declares max_declared_risk={agent.metadata.max_declared_risk} "
            f"but has a tool with risk {highest}"
        )
