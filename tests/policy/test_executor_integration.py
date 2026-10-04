"""tests/policy/test_executor_integration.py"""
from __future__ import annotations

import asyncio

import pytest

from core.policy.approval import ApprovalManager
from core.policy.config import PolicyConfig
from core.policy.engine import PolicyEngine
from core.tools.base import CancellationToken, Tool, ToolContext
from core.tools.executor import ToolExecutor, _summarize_args
from core.tools.metadata import RiskLevel, ToolCategory, ToolMetadata
from core.tools.registry import ToolRegistry
from core.tools.results import ToolResult
from core.tools.schemas import ToolSchema


class _RiskyTool(Tool):
    name = "risky_tool"
    description = "A tool with configurable risk for testing."
    schema = ToolSchema()

    def __init__(self, risk: RiskLevel):
        self.metadata = ToolMetadata(category=ToolCategory.SYSTEM, risk_level=risk, timeout_seconds=5)
        self.executed = False

    async def execute(self, args, context):
        self.executed = True
        return ToolResult.ok(self.name, data="done")


def _make_executor(risk: RiskLevel, policy_config: PolicyConfig, approval_timeout=1.0):
    import dataclasses
    tool = _RiskyTool(risk)
    registry = ToolRegistry()
    registry.register(tool)
    config = dataclasses.replace(policy_config, approval_timeout_seconds=approval_timeout)
    engine = PolicyEngine(config=config)
    manager = ApprovalManager()
    executor = ToolExecutor(registry, policy_engine=engine, approval_manager=manager)
    return tool, executor, manager


@pytest.mark.asyncio
async def test_low_risk_executes_immediately():
    tool, executor, _ = _make_executor(RiskLevel.LOW, PolicyConfig())
    result = await executor.execute("risky_tool", {}, ToolContext())
    assert result.success is True
    assert tool.executed is True


@pytest.mark.asyncio
async def test_denied_tool_never_executes():
    tool, executor, _ = _make_executor(RiskLevel.CRITICAL, PolicyConfig(allow_critical_commands=False))
    result = await executor.execute("risky_tool", {}, ToolContext())
    assert result.success is False
    assert result.error_type == "PolicyDeniedError"
    assert tool.executed is False


@pytest.mark.asyncio
async def test_approval_required_and_granted_executes():
    tool, executor, manager = _make_executor(RiskLevel.HIGH, PolicyConfig(), approval_timeout=5.0)

    async def approve_soon():
        await asyncio.sleep(0.1)
        for req_id in list(manager._requests.keys()):
            manager.approve(req_id)

    task = asyncio.ensure_future(approve_soon())
    result = await executor.execute("risky_tool", {}, ToolContext())
    await task

    assert result.success is True
    assert tool.executed is True


@pytest.mark.asyncio
async def test_approval_required_and_denied_never_executes():
    tool, executor, manager = _make_executor(RiskLevel.HIGH, PolicyConfig(), approval_timeout=5.0)

    async def deny_soon():
        await asyncio.sleep(0.1)
        for req_id in list(manager._requests.keys()):
            manager.deny(req_id, reason="not now")

    task = asyncio.ensure_future(deny_soon())
    result = await executor.execute("risky_tool", {}, ToolContext())
    await task

    assert result.success is False
    assert tool.executed is False


@pytest.mark.asyncio
async def test_approval_timeout_fails_and_never_executes():
    tool, executor, manager = _make_executor(RiskLevel.HIGH, PolicyConfig(), approval_timeout=0.2)
    result = await executor.execute("risky_tool", {}, ToolContext())
    assert result.success is False
    assert result.error_type == "ApprovalTimeoutError"
    assert tool.executed is False


@pytest.mark.asyncio
async def test_pre_approved_context_skips_wait():
    """A caller that already obtained approval out-of-band (e.g. re-submits
    after a prior APPROVAL_REQUIRED response) passes approval_id directly —
    the executor validates+consumes it immediately without waiting."""
    tool, executor, manager = _make_executor(RiskLevel.HIGH, PolicyConfig(), approval_timeout=5.0)

    summary = _summarize_args("risky_tool", {})
    req = manager.request("risky_tool", summary, RiskLevel.HIGH)
    manager.approve(req.approval_id)

    context = ToolContext(approval_id=req.approval_id)
    result = await executor.execute("risky_tool", {}, context)
    assert result.success is True
    assert tool.executed is True


@pytest.mark.asyncio
async def test_agent_exceeding_risk_limit_denied_before_execution():
    tool, executor, _ = _make_executor(RiskLevel.CRITICAL, PolicyConfig())
    context = ToolContext(agent_id="research_agent", agent_max_risk=RiskLevel.LOW)
    result = await executor.execute("risky_tool", {}, context)
    assert result.success is False
    assert result.error_type == "PolicyDeniedError"
    assert tool.executed is False


@pytest.mark.asyncio
async def test_remote_critical_denied():
    tool, executor, _ = _make_executor(RiskLevel.CRITICAL, PolicyConfig())
    context = ToolContext(source="dashboard")
    result = await executor.execute("risky_tool", {}, context)
    assert result.success is False
    assert tool.executed is False


@pytest.mark.asyncio
async def test_cancellation_while_awaiting_approval():
    tool, executor, manager = _make_executor(RiskLevel.HIGH, PolicyConfig(), approval_timeout=5.0)
    token = CancellationToken()

    async def cancel_soon():
        await asyncio.sleep(0.1)
        token.cancel()

    task = asyncio.ensure_future(cancel_soon())
    result = await executor.execute("risky_tool", {}, ToolContext(cancellation_token=token))
    await task

    assert result.success is False
    assert tool.executed is False


def test_sensitive_argument_redacted_in_action_summary():
    summary = _summarize_args("some_tool", {"api_key": "AIzaSuperSecret123", "city": "SF"})
    assert "AIzaSuperSecret123" not in summary
    assert "REDACTED" in summary
    assert "SF" in summary
