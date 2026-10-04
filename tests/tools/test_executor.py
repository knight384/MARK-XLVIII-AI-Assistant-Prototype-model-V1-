"""tests/tools/test_executor.py"""
from __future__ import annotations

import asyncio

import pytest
from .conftest import EchoTool, FailingTool, SlowTool, SyncStyleTool

from core.tools.base import Tool, ToolContext, ToolEvent
from core.tools.executor import ToolExecutor
from core.tools.metadata import RiskLevel, ToolCategory, ToolMetadata
from core.tools.results import ToolResult
from core.tools.schemas import ToolSchema


@pytest.mark.asyncio
async def test_executes_registered_tool(registry_with_echo):
    executor = ToolExecutor(registry_with_echo)
    result = await executor.execute("echo_tool", {"message": "hi"}, ToolContext())
    assert result.success is True
    assert result.data == "hi"


@pytest.mark.asyncio
async def test_unknown_tool_returns_structured_failure(empty_registry):
    executor = ToolExecutor(empty_registry)
    result = await executor.execute("nonexistent", {}, ToolContext())
    assert result.success is False
    assert result.error_type == "ToolNotFoundError"


@pytest.mark.asyncio
async def test_validation_error_returns_structured_failure(registry_with_echo):
    executor = ToolExecutor(registry_with_echo)
    result = await executor.execute("echo_tool", {}, ToolContext())  # missing required 'message'
    assert result.success is False
    assert result.error_type == "ToolValidationError"


@pytest.mark.asyncio
async def test_tool_exception_is_normalized_not_raised(empty_registry):
    empty_registry.register(FailingTool())
    executor = ToolExecutor(empty_registry)
    result = await executor.execute("failing_tool", {}, ToolContext())
    assert result.success is False
    assert result.error_type == "RuntimeError"
    assert "boom" in result.error


@pytest.mark.asyncio
async def test_timeout_produces_structured_failure(empty_registry):
    empty_registry.register(SlowTool())
    executor = ToolExecutor(empty_registry)
    result = await executor.execute("slow_tool", {}, ToolContext())
    assert result.success is False
    assert result.error_type == "ToolTimeoutError"


@pytest.mark.asyncio
async def test_sync_style_tool_via_run_in_executor(empty_registry):
    empty_registry.register(SyncStyleTool())
    executor = ToolExecutor(empty_registry)
    result = await executor.execute("sync_style_tool", {}, ToolContext())
    assert result.success is True
    assert result.data == "blocking done"


@pytest.mark.asyncio
async def test_duration_ms_recorded(registry_with_echo):
    executor = ToolExecutor(registry_with_echo)
    result = await executor.execute("echo_tool", {"message": "x"}, ToolContext())
    assert result.duration_ms is not None
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_verification_hook_invoked_when_supported(empty_registry):
    from core.tools.base import VerificationResult

    class VerifiedTool(Tool):
        name = "verified_tool"
        description = "x"
        schema = ToolSchema()
        metadata = ToolMetadata(category=ToolCategory.SYSTEM, risk_level=RiskLevel.LOW,
                                 supports_verification=True, timeout_seconds=5)

        async def execute(self, args, context):
            return ToolResult.ok(self.name, data="done")

        async def verify(self, result, context):
            return VerificationResult(verified=True, detail="looks good")

    empty_registry.register(VerifiedTool())
    executor = ToolExecutor(empty_registry)
    result = await executor.execute("verified_tool", {}, ToolContext())
    assert result.metadata["verification"]["verified"] is True


@pytest.mark.asyncio
async def test_verification_not_invoked_when_unsupported(registry_with_echo):
    executor = ToolExecutor(registry_with_echo)
    result = await executor.execute("echo_tool", {"message": "x"}, ToolContext())
    assert "verification" not in result.metadata


@pytest.mark.asyncio
async def test_audit_hook_receives_events(registry_with_echo):
    events: list[ToolEvent] = []
    executor = ToolExecutor(registry_with_echo, audit_hook=events.append)
    await executor.execute("echo_tool", {"message": "x"}, ToolContext())
    types_seen = [e.type for e in events]
    assert types_seen == ["started", "completed"]


@pytest.mark.asyncio
async def test_audit_hook_receives_failure_event(empty_registry):
    empty_registry.register(FailingTool())
    events: list[ToolEvent] = []
    executor = ToolExecutor(empty_registry, audit_hook=events.append)
    await executor.execute("failing_tool", {}, ToolContext())
    assert [e.type for e in events] == ["started", "failed"]


@pytest.mark.asyncio
async def test_broken_audit_hook_does_not_break_execution(registry_with_echo):
    def broken_hook(event):
        raise RuntimeError("audit hook is broken")

    executor = ToolExecutor(registry_with_echo, audit_hook=broken_hook)
    result = await executor.execute("echo_tool", {"message": "x"}, ToolContext())
    assert result.success is True  # tool result unaffected by a broken hook
