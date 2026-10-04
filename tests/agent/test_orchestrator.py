"""tests/agent/test_orchestrator.py"""
from __future__ import annotations

import pytest
from .conftest import EchoAgent, FailingAgent, make_fake_gateway

from core.agent.base import AgentCapability
from core.agent.orchestrator import Orchestrator
from core.agent.registry import AgentRegistry
from core.agent.task import StepStatus, TaskStatus
from core.tools.base import CancellationToken


def _make_orchestrator(tool_registry, tool_executor, plan_json, agents=None,
                        max_step_retries=1, max_execution_steps=20, max_delegations=20):
    gateway, provider = make_fake_gateway(plan_json)
    agent_registry = AgentRegistry()
    for agent in (agents or [EchoAgent()]):
        agent_registry.register(agent)
    orchestrator = Orchestrator(
        agent_registry=agent_registry, tool_registry=tool_registry, tool_executor=tool_executor,
        model_gateway=gateway, max_step_retries=max_step_retries,
        max_execution_steps=max_execution_steps, max_delegations=max_delegations,
    )
    return orchestrator, provider


@pytest.mark.asyncio
async def test_single_step_task_completes(tool_registry, tool_executor):
    plan = (
        '{"goal": "g", "steps": [{"id": "s1", "description": "echo something", '
        '"required_capabilities": ["research"], "tool": "echo_tool", "tool_args": {"message": "hi"}}]}'
    )
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan)
    task = await orchestrator.run_task("do a thing")

    assert task.status == TaskStatus.COMPLETED
    assert len(task.steps) == 1
    assert task.steps[0].status == StepStatus.COMPLETED


@pytest.mark.asyncio
async def test_multi_step_sequential_task_completes(tool_registry, tool_executor):
    plan = (
        '{"goal": "g", "steps": ['
        '{"id": "s1", "description": "a", "required_capabilities": ["research"], '
        '"tool": "echo_tool", "tool_args": {"message": "one"}}, '
        '{"id": "s2", "description": "b", "required_capabilities": ["research"], '
        '"tool": "echo_tool", "tool_args": {"message": "two"}, "dependencies": ["s1"]}'
        ']}'
    )
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan)
    task = await orchestrator.run_task("do two things")

    assert task.status == TaskStatus.COMPLETED
    assert [s.status for s in task.steps] == [StepStatus.COMPLETED, StepStatus.COMPLETED]


@pytest.mark.asyncio
async def test_agent_selection_by_capability(tool_registry, tool_executor):
    """Confirms deterministic capability-based selection, not hardcoded to one agent."""
    from core.agent.base import AgentCapability, AgentMetadata, ToolUsingAgent
    from core.llm.capabilities import ModelCapabilities
    from core.tools.metadata import RiskLevel

    class CodingAgent(ToolUsingAgent):
        agent_id = "coding_agent_test"
        name = "x"; description = "x"
        metadata = AgentMetadata(capabilities=(AgentCapability.CODING,), tool_names=("echo_tool",),
                                  model_requirements=ModelCapabilities(text_generation=True),
                                  max_declared_risk=RiskLevel.LOW)

    plan = (
        '{"goal": "g", "steps": [{"id": "s1", "description": "code something", '
        '"required_capabilities": ["coding"], "tool": "echo_tool", "tool_args": {"message": "coded"}}]}'
    )
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan,
                                          agents=[EchoAgent(), CodingAgent()])
    task = await orchestrator.run_task("write some code")

    assert task.steps[0].assigned_agent == "coding_agent_test"
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_no_matching_agent_fails_step_and_task(tool_registry, tool_executor):
    plan = (
        '{"goal": "g", "steps": [{"id": "s1", "description": "x", "required_capabilities": ["coding"]}]}'
    )
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan, agents=[EchoAgent()])  # only research capability
    task = await orchestrator.run_task("goal")

    assert task.status == TaskStatus.FAILED
    assert task.steps[0].status == StepStatus.FAILED
    assert "No registered agent" in task.steps[0].error


@pytest.mark.asyncio
async def test_partial_failure_is_visible_not_hidden(tool_registry, tool_executor):
    plan = (
        '{"goal": "g", "steps": ['
        '{"id": "s1", "description": "a", "required_capabilities": ["research"], '
        '"tool": "echo_tool", "tool_args": {"message": "ok"}}, '
        '{"id": "s2", "description": "b", "required_capabilities": ["research"], '
        '"tool": "failing_tool", "tool_args": {}}'
        ']}'
    )
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan)
    task = await orchestrator.run_task("goal")

    assert task.status == TaskStatus.FAILED  # not silently reported as COMPLETED
    assert task.steps[0].status == StepStatus.COMPLETED
    assert task.steps[1].status == StepStatus.FAILED
    assert len(task.errors) >= 1


@pytest.mark.asyncio
async def test_dependent_step_skipped_when_dependency_fails(tool_registry, tool_executor):
    plan = (
        '{"goal": "g", "steps": ['
        '{"id": "s1", "description": "a", "required_capabilities": ["research"], '
        '"tool": "failing_tool", "tool_args": {}}, '
        '{"id": "s2", "description": "b", "required_capabilities": ["research"], '
        '"tool": "echo_tool", "tool_args": {"message": "x"}, "dependencies": ["s1"]}'
        ']}'
    )
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan)
    task = await orchestrator.run_task("goal")

    assert task.steps[0].status == StepStatus.FAILED
    assert task.steps[1].status == StepStatus.SKIPPED


@pytest.mark.asyncio
async def test_agent_retry_on_failure_within_bound(tool_registry, tool_executor):
    """FailingAgent always raises — confirms the retry loop respects max_step_retries
    and doesn't retry forever."""
    plan = '{"goal": "g", "steps": [{"id": "s1", "description": "x", "required_capabilities": ["research"]}]}'
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan,
                                          agents=[FailingAgent()], max_step_retries=3)
    task = await orchestrator.run_task("goal")

    assert task.status == TaskStatus.FAILED
    assert task.steps[0].attempts == 3  # retried exactly max_step_retries times, not forever


@pytest.mark.asyncio
async def test_planning_failure_marks_task_failed_not_raised(tool_registry, tool_executor):
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, "not valid json")
    task = await orchestrator.run_task("goal")  # must not raise

    assert task.status == TaskStatus.FAILED
    assert task.errors


@pytest.mark.asyncio
async def test_cancellation_before_start(tool_registry, tool_executor):
    plan = '{"goal": "g", "steps": [{"id": "s1", "description": "x", "required_capabilities": ["research"]}]}'
    orchestrator, provider = _make_orchestrator(tool_registry, tool_executor, plan)
    token = CancellationToken()
    token.cancel()

    task = await orchestrator.run_task("goal", cancellation_token=token)

    assert task.status == TaskStatus.CANCELLED
    assert len(provider.calls) == 0  # never even reached planning


@pytest.mark.asyncio
async def test_cancellation_mid_execution_stops_remaining_steps(tool_registry, tool_executor):
    plan = (
        '{"goal": "g", "steps": ['
        '{"id": "s1", "description": "a", "required_capabilities": ["research"], '
        '"tool": "echo_tool", "tool_args": {"message": "x"}}, '
        '{"id": "s2", "description": "b", "required_capabilities": ["research"], '
        '"tool": "echo_tool", "tool_args": {"message": "y"}}'
        ']}'
    )
    gateway, _ = make_fake_gateway(plan)
    agent_registry = AgentRegistry()

    class CancellingAgent(EchoAgent.__mro__[0]):
        pass

    # Simplest deterministic way to test mid-run cancellation: cancel the
    # token from within a custom agent's handle() before returning.
    from core.agent.base import AgentCapability, AgentMetadata, ToolUsingAgent
    from core.llm.capabilities import ModelCapabilities
    from core.tools.metadata import RiskLevel

    token = CancellationToken()

    class CancelOnFirstCallAgent(ToolUsingAgent):
        agent_id = "cancel_on_first_call"
        name = "x"; description = "x"
        metadata = AgentMetadata(capabilities=(AgentCapability.RESEARCH,), tool_names=("echo_tool",),
                                  model_requirements=ModelCapabilities(text_generation=True),
                                  max_declared_risk=RiskLevel.LOW)

        async def handle(self, step, context):
            result = await super().handle(step, context)
            token.cancel()  # cancel only after this step's real work is done
            return result

    agent_registry.register(CancelOnFirstCallAgent())
    orchestrator = Orchestrator(agent_registry=agent_registry, tool_registry=tool_registry,
                                 tool_executor=tool_executor, model_gateway=gateway)

    task = await orchestrator.run_task("goal", cancellation_token=token)

    assert task.status == TaskStatus.CANCELLED
    # first step ran (it triggered the cancel), second step never got the chance
    assert task.steps[0].status == StepStatus.COMPLETED
    assert task.steps[1].status == StepStatus.CANCELLED


@pytest.mark.asyncio
async def test_max_execution_steps_loop_protection(tool_registry, tool_executor):
    steps_json = ", ".join(
        f'{{"id": "s{i}", "description": "x", "required_capabilities": ["research"], '
        f'"tool": "echo_tool", "tool_args": {{"message": "x"}}}}'
        for i in range(10)
    )
    plan = f'{{"goal": "g", "steps": [{steps_json}]}}'
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan, max_execution_steps=3)

    task = await orchestrator.run_task("goal")

    assert task.status == TaskStatus.FAILED
    assert any("max_execution_steps" in e for e in task.errors)


@pytest.mark.asyncio
async def test_max_delegations_loop_protection(tool_registry, tool_executor):
    steps_json = ", ".join(
        f'{{"id": "s{i}", "description": "x", "required_capabilities": ["research"], '
        f'"tool": "echo_tool", "tool_args": {{"message": "x"}}}}'
        for i in range(5)
    )
    plan = f'{{"goal": "g", "steps": [{steps_json}]}}'
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan,
                                          max_execution_steps=20, max_delegations=2)

    task = await orchestrator.run_task("goal")

    assert task.status == TaskStatus.FAILED
    assert any("max_delegations" in e for e in task.errors)


@pytest.mark.asyncio
async def test_preferred_agent_from_plan_is_honored(tool_registry, tool_executor):
    plan = (
        '{"goal": "g", "steps": [{"id": "s1", "description": "x", '
        '"required_capabilities": ["research"], "preferred_agent": "echo_agent", '
        '"tool": "echo_tool", "tool_args": {"message": "x"}}]}'
    )
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan)
    task = await orchestrator.run_task("goal")

    assert task.steps[0].assigned_agent == "echo_agent"


@pytest.mark.asyncio
async def test_task_observations_are_populated(tool_registry, tool_executor):
    plan = (
        '{"goal": "g", "steps": [{"id": "s1", "description": "x", "required_capabilities": ["research"], '
        '"tool": "echo_tool", "tool_args": {"message": "x"}}]}'
    )
    orchestrator, _ = _make_orchestrator(tool_registry, tool_executor, plan)
    task = await orchestrator.run_task("goal")

    obs_types = [o.type for o in task.observations]
    assert "task_created" in obs_types
    assert "plan_generated" in obs_types
    assert "step_started" in obs_types
    assert "step_completed" in obs_types
    assert "task_finished" in obs_types
