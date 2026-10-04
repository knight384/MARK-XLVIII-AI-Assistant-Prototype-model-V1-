"""tests/agent/test_agent_interface.py"""
from __future__ import annotations

from .conftest import EchoAgent

from core.llm.capabilities import ModelCapabilities
from core.tools.metadata import RiskLevel


def test_agent_has_id_name_description_metadata():
    agent = EchoAgent()
    assert agent.agent_id == "echo_agent"
    assert agent.name
    assert agent.description
    assert agent.metadata.max_declared_risk == RiskLevel.LOW


def test_agent_declares_capabilities():
    from core.agent.base import AgentCapability
    agent = EchoAgent()
    assert AgentCapability.RESEARCH in agent.metadata.capabilities


def test_agent_declares_model_requirements():
    agent = EchoAgent()
    assert isinstance(agent.metadata.model_requirements, ModelCapabilities)


def test_agent_declares_tool_names():
    agent = EchoAgent()
    assert "echo_tool" in agent.metadata.tool_names
