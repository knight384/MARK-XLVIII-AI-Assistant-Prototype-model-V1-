"""
tests/agent/conftest.py — shared fixtures for the Phase 4 agent-runtime test
suite.

Deliberately uses FRESH, isolated ToolRegistry/AgentRegistry/ModelGateway
instances per test rather than the process-wide singletons
(core.tools.get_default_registry(), core.agent.get_default_agent_registry())
— those singletons are also used by tests/tools/ and tests/llm/, and
mutating them here would make test outcomes depend on execution order.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.agent.base import Agent, AgentCapability, AgentMetadata, ToolUsingAgent
from core.agent.context import AgentContext
from core.agent.registry import AgentRegistry
from core.agent.result import AgentResult
from core.agent.task import TaskStep
from core.llm.capabilities import ModelCapabilities
from core.llm.gateway import ModelGateway
from core.llm.registry import ProviderRegistry
from core.llm.router import ModelRouter
from core.llm.types import ModelResponse
from core.llm.providers.base import HealthStatus, ModelInfo, Provider
from core.tools.base import CancellationToken, Tool, ToolContext
from core.tools.executor import ToolExecutor
from core.tools.metadata import Capability, RiskLevel, ToolCategory, ToolMetadata
from core.tools.registry import ToolRegistry
from core.tools.results import ToolResult
from core.tools.schemas import ParamSchema, ToolSchema


# -- fake tools (mirrors tests/tools/conftest.py's EchoTool pattern) -------

class EchoTool(Tool):
    name = "echo_tool"
    description = "Echoes its input back."
    schema = ToolSchema((ParamSchema("message", "string", required=True),))
    metadata = ToolMetadata(category=ToolCategory.SYSTEM, risk_level=RiskLevel.LOW, timeout_seconds=5)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        return ToolResult.ok(self.name, data=args.get("message", ""))


class FailingTool(Tool):
    name = "failing_tool"
    description = "Always fails."
    schema = ToolSchema()
    metadata = ToolMetadata(category=ToolCategory.SYSTEM, risk_level=RiskLevel.LOW, timeout_seconds=5)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        return ToolResult.fail(self.name, error="deliberate failure", error_type="RuntimeError")


# -- a fake, fully in-memory model provider (mirrors tests/llm/conftest.py) -

class FakeModelProvider(Provider):
    """A minimal fake Provider, used to build a fully isolated ModelGateway
    with no real network/SDK calls, so Planner/agent 'ask the model' paths
    are testable deterministically (Phase 4 spec Part 40: mock providers/
    models)."""

    provider_id = "fake"
    display_name = "Fake"

    def __init__(self, response_text: str = '{"tool": "echo_tool", "arguments": {"message": "hi"}}'):
        self._response_text = response_text
        self.calls: list = []

    def list_models(self):
        return [ModelInfo(model_id="gemini-2.5-flash", provider_id=self.provider_id, display_name="fake-model",
                           capabilities=ModelCapabilities(text_generation=True, tool_calling=True))]

    def is_configured(self) -> bool:
        return True

    def health_check(self):
        return HealthStatus(healthy=True)

    def generate(self, request, model_id: str) -> ModelResponse:
        self.calls.append((request, model_id))
        return ModelResponse(content=self._response_text, provider=self.provider_id, model=model_id)


def make_fake_gateway(response_text: str | None = None) -> tuple[ModelGateway, FakeModelProvider]:
    provider = FakeModelProvider(response_text) if response_text else FakeModelProvider()
    registry = ProviderRegistry()
    registry.register("gemini", lambda: provider)
    registry.register("fake", lambda: provider)
    router = ModelRouter(registry)
    gateway = ModelGateway(registry=registry, router=router)
    return gateway, provider


# -- fixtures ------------------------------------------------------------

@pytest.fixture
def tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(EchoTool())
    reg.register(FailingTool())
    return reg


@pytest.fixture
def tool_executor(tool_registry) -> ToolExecutor:
    return ToolExecutor(tool_registry)


@pytest.fixture
def agent_registry() -> AgentRegistry:
    return AgentRegistry()


@pytest.fixture
def fake_gateway():
    return make_fake_gateway()[0]


def make_context(tool_registry, tool_executor, model_gateway=None, task=None,
                  cancellation_token=None) -> AgentContext:
    return AgentContext(
        task=task, request_id="test-req", model_gateway=model_gateway,
        tool_registry=tool_registry, tool_executor=tool_executor,
        cancellation_token=cancellation_token or CancellationToken(),
    )


class EchoAgent(ToolUsingAgent):
    """A minimal concrete agent for interface/registry tests."""
    agent_id = "echo_agent"
    name = "Echo Agent"
    description = "Echoes things via echo_tool."
    metadata = AgentMetadata(
        capabilities=(AgentCapability.RESEARCH,),
        tool_names=("echo_tool",),
        model_requirements=ModelCapabilities(text_generation=True),
        max_declared_risk=RiskLevel.LOW,
    )


class FailingAgent(Agent):
    agent_id = "failing_agent"
    name = "Failing Agent"
    description = "Always raises."
    metadata = AgentMetadata(capabilities=(AgentCapability.RESEARCH,), max_declared_risk=RiskLevel.LOW)

    async def handle(self, step: TaskStep, context: AgentContext) -> AgentResult:
        raise RuntimeError("boom")
