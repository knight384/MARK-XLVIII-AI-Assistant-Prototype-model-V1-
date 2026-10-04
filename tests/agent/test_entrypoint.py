"""tests/agent/test_entrypoint.py"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.agent.entrypoint import RunAgentTaskTool, register_agent_tools
from core.agent.task import StepStatus, Task, TaskStatus, TaskStep
from core.tools.base import ToolContext
from core.tools.registry import ToolRegistry


def test_register_agent_tools_adds_run_agent_task():
    registry = ToolRegistry()
    register_agent_tools(registry)
    assert registry.exists("run_agent_task")


def test_register_agent_tools_is_idempotent_safe():
    registry = ToolRegistry()
    register_agent_tools(registry)
    register_agent_tools(registry)  # must not raise a second time
    assert registry.exists("run_agent_task")


def test_run_agent_task_metadata():
    tool = RunAgentTaskTool()
    assert tool.metadata.timeout_seconds and tool.metadata.timeout_seconds > 60
    assert tool.schema.required_names() == ["goal"]


@pytest.mark.asyncio
async def test_run_agent_task_missing_goal_fails_validation():
    tool = RunAgentTaskTool()
    result = await tool.execute({}, ToolContext())
    assert result.success is False
    assert result.error_type == "ToolValidationError"


@pytest.mark.asyncio
async def test_run_agent_task_reports_success():
    completed_task = Task(goal="do X", status=TaskStatus.COMPLETED, steps=[
        TaskStep(step_id="s1", description="did X", status=StepStatus.COMPLETED),
    ])
    fake_orchestrator = MagicMock()
    fake_orchestrator.run_task = AsyncMock(return_value=completed_task)

    with patch("core.agent.orchestrator.get_default_orchestrator", return_value=fake_orchestrator):
        tool = RunAgentTaskTool()
        result = await tool.execute({"goal": "do X"}, ToolContext())

    assert result.success is True
    assert "COMPLETED" in result.data


@pytest.mark.asyncio
async def test_run_agent_task_reports_failure_without_raising():
    failed_task = Task(goal="do X", status=TaskStatus.FAILED, steps=[
        TaskStep(step_id="s1", description="did X", status=StepStatus.FAILED, error="boom"),
    ], errors=["boom"])
    fake_orchestrator = MagicMock()
    fake_orchestrator.run_task = AsyncMock(return_value=failed_task)

    with patch("core.agent.orchestrator.get_default_orchestrator", return_value=fake_orchestrator):
        tool = RunAgentTaskTool()
        result = await tool.execute({"goal": "do X"}, ToolContext())

    assert result.success is False
    assert "boom" in result.error
