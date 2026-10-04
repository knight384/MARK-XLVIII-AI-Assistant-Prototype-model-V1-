"""tests/agent/test_tool_using_agent.py"""
from __future__ import annotations

import pytest
from .conftest import EchoAgent, make_context, make_fake_gateway

from core.agent.task import TaskStep
from core.tools.base import CancellationToken


@pytest.mark.asyncio
async def test_explicit_tool_routing_skips_model_call(tool_registry, tool_executor):
    gateway, provider = make_fake_gateway()
    agent = EchoAgent()
    step = TaskStep(step_id="s1", description="echo hi", tool_name="echo_tool",
                     tool_args={"message": "explicit"})
    context = make_context(tool_registry, tool_executor, model_gateway=gateway)

    result = await agent.handle(step, context)

    assert result.success is True
    assert result.summary == "explicit"
    assert len(provider.calls) == 0  # no model call needed — routing was explicit


@pytest.mark.asyncio
async def test_model_assisted_tool_selection(tool_registry, tool_executor):
    gateway, provider = make_fake_gateway('{"tool": "echo_tool", "arguments": {"message": "from model"}}')
    agent = EchoAgent()
    step = TaskStep(step_id="s1", description="echo something")  # no explicit tool_name
    context = make_context(tool_registry, tool_executor, model_gateway=gateway)

    result = await agent.handle(step, context)

    assert result.success is True
    assert result.summary == "from model"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_tool_outside_declared_set_is_rejected(tool_registry, tool_executor):
    gateway, _ = make_fake_gateway()
    agent = EchoAgent()  # only declares "echo_tool"
    step = TaskStep(step_id="s1", description="x", tool_name="failing_tool", tool_args={})
    context = make_context(tool_registry, tool_executor, model_gateway=gateway)

    result = await agent.handle(step, context)

    assert result.success is False
    assert "outside this agent's declared tool set" in result.summary


@pytest.mark.asyncio
async def test_model_selecting_disallowed_tool_is_rejected(tool_registry, tool_executor):
    gateway, _ = make_fake_gateway('{"tool": "failing_tool", "arguments": {}}')
    agent = EchoAgent()
    step = TaskStep(step_id="s1", description="x")
    context = make_context(tool_registry, tool_executor, model_gateway=gateway)

    result = await agent.handle(step, context)

    assert result.success is False


@pytest.mark.asyncio
async def test_tool_failure_propagates_as_agent_failure(tool_registry, tool_executor):
    from core.agent.base import AgentCapability, AgentMetadata, ToolUsingAgent
    from core.llm.capabilities import ModelCapabilities
    from core.tools.metadata import RiskLevel

    class FailingToolAgent(ToolUsingAgent):
        agent_id = "failing_tool_agent"
        name = "x"
        description = "x"
        metadata = AgentMetadata(capabilities=(AgentCapability.RESEARCH,), tool_names=("failing_tool",),
                                  model_requirements=ModelCapabilities(text_generation=True),
                                  max_declared_risk=RiskLevel.LOW)

    gateway, _ = make_fake_gateway()
    agent = FailingToolAgent()
    step = TaskStep(step_id="s1", description="x", tool_name="failing_tool", tool_args={})
    context = make_context(tool_registry, tool_executor, model_gateway=gateway)

    result = await agent.handle(step, context)

    assert result.success is False
    assert "deliberate failure" in (result.errors[0] if result.errors else "")


@pytest.mark.asyncio
async def test_cancelled_before_start_short_circuits(tool_registry, tool_executor):
    gateway, provider = make_fake_gateway()
    agent = EchoAgent()
    step = TaskStep(step_id="s1", description="x", tool_name="echo_tool", tool_args={"message": "x"})
    token = CancellationToken()
    token.cancel()
    context = make_context(tool_registry, tool_executor, model_gateway=gateway, cancellation_token=token)

    result = await agent.handle(step, context)

    assert result.success is False
    assert len(provider.calls) == 0


@pytest.mark.asyncio
async def test_agent_observations_include_tool_result(tool_registry, tool_executor):
    gateway, _ = make_fake_gateway()
    agent = EchoAgent()
    step = TaskStep(step_id="s1", description="x", tool_name="echo_tool", tool_args={"message": "hi"})
    context = make_context(tool_registry, tool_executor, model_gateway=gateway)

    result = await agent.handle(step, context)

    assert len(result.observations) == 1
    assert result.observations[0].source == "tool"
    assert result.observations[0].related_step == "s1"
