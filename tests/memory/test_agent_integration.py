"""
tests/memory/test_agent_integration.py — Phase 5 spec Part 41 "Agent
integration" tests: AgentContext.memory, Orchestrator memory retrieval,
Planner memory retrieval, DeveloperAgent project memory.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.agent.agents import DeveloperAgent
from core.agent.context import AgentContext
from core.agent.orchestrator import Orchestrator
from core.agent.planner import Planner
from core.agent.registry import AgentRegistry
from core.agent.task import TaskStep
from core.memory.models import MemoryType, Source
from core.memory.policies import MemoryConfig
from core.memory.service import MemoryService
from core.tools.base import CancellationToken


def _fake_gateway(response_text):
    """Mirrors tests/agent/conftest.py's make_fake_gateway, duplicated
    locally to keep tests/memory/ self-contained (small, deliberate
    duplication of a test fixture, not production code)."""
    from core.llm.gateway import ModelGateway
    from core.llm.providers.base import HealthStatus, ModelInfo, Provider
    from core.llm.registry import ProviderRegistry
    from core.llm.router import ModelRouter
    from core.llm.capabilities import ModelCapabilities
    from core.llm.types import ModelResponse

    class FakeProvider(Provider):
        provider_id = "gemini"
        display_name = "fake"

        def __init__(self):
            self.calls = []

        def list_models(self):
            return [ModelInfo(model_id="gemini-2.5-flash", provider_id="gemini", display_name="fake",
                               capabilities=ModelCapabilities(text_generation=True, tool_calling=True))]

        def is_configured(self): return True
        def health_check(self): return HealthStatus(healthy=True)

        def generate(self, request, model_id):
            self.calls.append(request)
            return ModelResponse(content=response_text, provider=self.provider_id, model=model_id)

    provider = FakeProvider()
    registry = ProviderRegistry()
    registry.register("gemini", lambda: provider)
    router = ModelRouter(registry)
    return ModelGateway(registry=registry, router=router), provider


# -- AgentContext.memory ---------------------------------------------------

def test_agent_context_exposes_memory(memory_service):
    context = AgentContext(memory=memory_service)
    assert context.memory is memory_service


def test_agent_context_retrieve_memory_convenience(memory_service):
    memory_service.remember("User likes dark mode", MemoryType.SEMANTIC, source=Source.USER)
    context = AgentContext(memory=memory_service)
    results = context.retrieve_memory("dark mode")
    assert len(results) == 1


def test_agent_context_retrieve_memory_returns_empty_without_service():
    context = AgentContext(memory=None)
    assert context.retrieve_memory("anything") == []


def test_agent_context_retrieve_memory_survives_service_failure(memory_service, monkeypatch):
    def broken_retrieve(*a, **kw):
        raise RuntimeError("storage exploded")
    monkeypatch.setattr(memory_service, "retrieve", broken_retrieve)
    context = AgentContext(memory=memory_service)
    assert context.retrieve_memory("anything") == []  # must not raise


# -- Orchestrator memory integration ---------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_retrieves_memory_before_planning(memory_service):
    from tests.tools.conftest import EchoTool  # reuse Phase 3's simple fake tool
    from core.tools.registry import ToolRegistry
    from core.tools.executor import ToolExecutor
    from core.agent.base import AgentCapability, AgentMetadata, ToolUsingAgent
    from core.llm.capabilities import ModelCapabilities
    from core.tools.metadata import RiskLevel

    memory_service.remember("The project uses SQLite for storage", MemoryType.SEMANTIC, source=Source.USER)

    tool_registry = ToolRegistry()
    tool_registry.register(EchoTool())
    tool_executor = ToolExecutor(tool_registry)

    class EchoAgent(ToolUsingAgent):
        agent_id = "echo_agent"; name = "x"; description = "x"
        metadata = AgentMetadata(capabilities=(AgentCapability.RESEARCH,), tool_names=("echo_tool",),
                                  model_requirements=ModelCapabilities(text_generation=True),
                                  max_declared_risk=RiskLevel.LOW)

    plan_json = (
        '{"goal": "g", "steps": [{"id": "s1", "description": "x", '
        '"required_capabilities": ["research"], "tool": "echo_tool", "tool_args": {"message": "hi"}}]}'
    )
    gateway, provider = _fake_gateway(plan_json)
    agent_registry = AgentRegistry()
    agent_registry.register(EchoAgent())

    orchestrator = Orchestrator(agent_registry=agent_registry, tool_registry=tool_registry,
                                 tool_executor=tool_executor, model_gateway=gateway,
                                 memory_service=memory_service)
    await orchestrator.run_task("what storage does the project use")

    # The planning prompt should have included retrieved memory context.
    planning_call = provider.calls[0]
    assert "SQLite" in planning_call.messages[0].content


@pytest.mark.asyncio
async def test_orchestrator_does_not_crash_when_memory_retrieval_fails():
    from core.tools.registry import ToolRegistry
    from core.tools.executor import ToolExecutor
    from tests.tools.conftest import EchoTool

    tool_registry = ToolRegistry()
    tool_registry.register(EchoTool())
    tool_executor = ToolExecutor(tool_registry)

    class BrokenMemory:
        config = MemoryConfig()
        def retrieve(self, *a, **kw):
            raise RuntimeError("boom")

    plan_json = '{"goal": "g", "steps": [{"id": "s1", "description": "x", "required_capabilities": ["research"]}]}'
    gateway, _ = _fake_gateway(plan_json)
    orchestrator = Orchestrator(agent_registry=AgentRegistry(), tool_registry=tool_registry,
                                 tool_executor=tool_executor, model_gateway=gateway,
                                 memory_service=BrokenMemory())
    task = await orchestrator.run_task("goal")  # must not raise
    assert task is not None


@pytest.mark.asyncio
async def test_orchestrator_records_episodic_outcome_on_completion(memory_service):
    from core.tools.registry import ToolRegistry
    from core.tools.executor import ToolExecutor
    from tests.tools.conftest import EchoTool
    from core.agent.base import AgentCapability, AgentMetadata, ToolUsingAgent
    from core.llm.capabilities import ModelCapabilities
    from core.tools.metadata import RiskLevel

    tool_registry = ToolRegistry()
    tool_registry.register(EchoTool())
    tool_executor = ToolExecutor(tool_registry)

    class EchoAgent(ToolUsingAgent):
        agent_id = "echo_agent"; name = "x"; description = "x"
        metadata = AgentMetadata(capabilities=(AgentCapability.RESEARCH,), tool_names=("echo_tool",),
                                  model_requirements=ModelCapabilities(text_generation=True),
                                  max_declared_risk=RiskLevel.LOW)

    plan_json = (
        '{"goal": "do the thing", "steps": [{"id": "s1", "description": "x", '
        '"required_capabilities": ["research"], "tool": "echo_tool", "tool_args": {"message": "hi"}}]}'
    )
    gateway, _ = _fake_gateway(plan_json)
    agent_registry = AgentRegistry()
    agent_registry.register(EchoAgent())

    orchestrator = Orchestrator(agent_registry=agent_registry, tool_registry=tool_registry,
                                 tool_executor=tool_executor, model_gateway=gateway,
                                 memory_service=memory_service)
    task = await orchestrator.run_task("do the thing")

    recent = memory_service.episodic.recent(limit=5)
    assert any(task.task_id == r.metadata.get("related_task") for r in recent)


# -- Planner memory integration --------------------------------------------

@pytest.mark.asyncio
async def test_planner_includes_memory_context_in_prompt():
    plan_json = '{"goal": "g", "steps": [{"id": "s1", "description": "x", "required_capabilities": ["research"]}]}'
    gateway, provider = _fake_gateway(plan_json)
    planner = Planner(model_gateway=gateway)
    await planner.plan("goal", memory_context="Known constraint: must use Python 3.10+")
    assert "Python 3.10+" in provider.calls[0].messages[0].content


@pytest.mark.asyncio
async def test_planner_works_without_memory_context():
    plan_json = '{"goal": "g", "steps": [{"id": "s1", "description": "x", "required_capabilities": ["research"]}]}'
    gateway, _ = _fake_gateway(plan_json)
    planner = Planner(model_gateway=gateway)
    steps = await planner.plan("goal")  # no memory_context supplied
    assert len(steps) == 1


# -- DeveloperAgent project memory -----------------------------------------

@pytest.mark.asyncio
async def test_developer_agent_retrieves_project_memory(memory_service):
    from core.tools.registry import ToolRegistry
    from core.tools.executor import ToolExecutor
    from core.tools.base import Tool
    from core.tools.metadata import ToolCategory, RiskLevel as ToolRisk, ToolMetadata as ToolMeta
    from core.tools.schemas import ToolSchema, ParamSchema
    from core.tools.results import ToolResult

    captured_args = {}

    class CapturingTool(Tool):
        name = "dev_agent"
        description = "x"
        schema = ToolSchema((ParamSchema("description", "string", required=True),))
        metadata = ToolMeta(category=ToolCategory.DEVELOPER, risk_level=ToolRisk.CRITICAL, timeout_seconds=5)

        async def execute(self, args, context):
            captured_args.update(args)
            return ToolResult.ok(self.name, data="done")

    tool_registry = ToolRegistry()
    tool_registry.register(CapturingTool())
    tool_executor = ToolExecutor(tool_registry)

    project_id = "test-project"
    memory_service.projects.set_fact(project_id, "tech_stack", "Python + FastAPI")
    memory_service.projects.set_fact(project_id, "known_issue", "flaky integration test")

    agent = DeveloperAgent()
    step = TaskStep(step_id="s1", description="fix the bug", tool_name="dev_agent",
                     tool_args={"description": "fix the bug"})
    context = AgentContext(
        tool_registry=tool_registry, tool_executor=tool_executor, memory=memory_service,
        cancellation_token=CancellationToken(), shared={"project_id": project_id},
    )

    result = await agent.handle(step, context)

    assert result.success is True
    assert "Python + FastAPI" in captured_args["description"]
    assert "flaky integration test" in captured_args["description"]


@pytest.mark.asyncio
async def test_developer_agent_works_without_project_id(memory_service):
    """No project_id in context.shared -> DeveloperAgent behaves like a
    plain ToolUsingAgent, no crash."""
    from core.tools.registry import ToolRegistry
    from core.tools.executor import ToolExecutor
    from tests.tools.conftest import EchoTool

    tool_registry = ToolRegistry()

    class DevAgentEcho(EchoTool):
        name = "dev_agent"

    tool_registry.register(DevAgentEcho())
    tool_executor = ToolExecutor(tool_registry)

    agent = DeveloperAgent()
    step = TaskStep(step_id="s1", description="x", tool_name="dev_agent", tool_args={"message": "hi"})
    context = AgentContext(tool_registry=tool_registry, tool_executor=tool_executor,
                            memory=memory_service, cancellation_token=CancellationToken(), shared={})

    result = await agent.handle(step, context)
    assert result.success is True


@pytest.mark.asyncio
async def test_developer_agent_records_outcome_to_project_memory(memory_service):
    from core.tools.registry import ToolRegistry
    from core.tools.executor import ToolExecutor
    from tests.tools.conftest import EchoTool

    tool_registry = ToolRegistry()

    class DevAgentEcho(EchoTool):
        name = "dev_agent"

    tool_registry.register(DevAgentEcho())
    tool_executor = ToolExecutor(tool_registry)

    project_id = "proj-x"
    agent = DeveloperAgent()
    step = TaskStep(step_id="s1", description="x", tool_name="dev_agent", tool_args={"message": "fixed it"})
    context = AgentContext(tool_registry=tool_registry, tool_executor=tool_executor,
                            memory=memory_service, cancellation_token=CancellationToken(),
                            shared={"project_id": project_id})

    await agent.handle(step, context)

    facts = memory_service.projects.get_facts(project_id, field="last_dev_agent_outcome")
    assert len(facts) == 1
