"""tests/tools/conftest.py — shared fixtures for the Phase 3 tool-layer test suite."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.tools.base import Tool, ToolContext
from core.tools.metadata import Capability, RiskLevel, ToolCategory, ToolMetadata
from core.tools.registry import ToolRegistry
from core.tools.results import ToolResult
from core.tools.schemas import ParamSchema, ToolSchema


class EchoTool(Tool):
    """A minimal, fully-controllable fake Tool for registry/executor tests."""
    name = "echo_tool"
    description = "Echoes its input back."
    schema = ToolSchema((
        ParamSchema("message", "string", "The message to echo", required=True),
        ParamSchema("shout", "boolean", "Uppercase the message"),
        ParamSchema("mode", "string", "one of a|b|c", enum=("a", "b", "c")),
        ParamSchema("count", "integer", "repeat count"),
    ))
    metadata = ToolMetadata(category=ToolCategory.SYSTEM, risk_level=RiskLevel.LOW, timeout_seconds=5)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        msg = args.get("message", "")
        if args.get("shout"):
            msg = msg.upper()
        return ToolResult.ok(self.name, data=msg)


class FailingTool(Tool):
    name = "failing_tool"
    description = "Always raises."
    schema = ToolSchema()
    metadata = ToolMetadata(category=ToolCategory.SYSTEM, risk_level=RiskLevel.LOW, timeout_seconds=5)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        raise RuntimeError("boom")


class SlowTool(Tool):
    name = "slow_tool"
    description = "Sleeps longer than its timeout."
    schema = ToolSchema()
    metadata = ToolMetadata(category=ToolCategory.SYSTEM, risk_level=RiskLevel.LOW, timeout_seconds=0.05)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        import asyncio
        await asyncio.sleep(1.0)
        return ToolResult.ok(self.name, data="should never get here")


class SyncStyleTool(Tool):
    """Simulates the common pattern: an async wrapper around a blocking call
    via run_in_executor, like the real actions/*.py wrappers use."""
    name = "sync_style_tool"
    description = "Wraps a blocking call."
    schema = ToolSchema()
    metadata = ToolMetadata(category=ToolCategory.SYSTEM, risk_level=RiskLevel.LOW, timeout_seconds=5)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        import asyncio
        def blocking():
            import time
            time.sleep(0.01)
            return "blocking done"
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, blocking)
        return ToolResult.ok(self.name, data=r)


@pytest.fixture
def empty_registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def registry_with_echo(empty_registry) -> ToolRegistry:
    empty_registry.register(EchoTool())
    return empty_registry
