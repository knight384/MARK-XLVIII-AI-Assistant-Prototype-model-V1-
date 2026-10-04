"""
core.agent — the multi-agent runtime (Phase 4).

Typical usage (main.py, once at startup, right after Phase 3's tool registry
and executor are constructed):

    from core.agent import register_agent_tools
    register_agent_tools(_tool_registry)

That's the ONLY main.py change this phase requires — Gemini Live's existing
realtime loop and _execute_tool routing are otherwise completely untouched;
the new `run_agent_task` tool is handled generically like every other tool.

Direct orchestration (e.g. from a script, or a future non-voice entry point):

    from core.agent import get_default_orchestrator
    task = await get_default_orchestrator().run_task("research X and recommend Y")
    print(task.summary())
"""
from .agents import (
    BrowserAgent, ComputerAgent, DeveloperAgent, FileDocumentAgent,
    ResearchAgent, VerificationAgent, register_all_agents,
)
from .base import Agent, AgentCapability, AgentMetadata, ToolUsingAgent
from .complexity import is_complex_request
from .context import AgentContext
from .entrypoint import RunAgentTaskTool, register_agent_tools
from .errors import (
    AgentError, AgentNotFoundError, AgentRegistrationError, InvalidPlanError,
    MaxDelegationsExceededError, MaxStepsExceededError, OrchestrationError,
    PlanningError, TaskCancelledError,
)
from .orchestrator import Orchestrator, get_default_orchestrator
from .planner import Planner
from .registry import AgentRegistry, get_default_agent_registry
from .result import AgentResult, Observation
from .task import StepStatus, Task, TaskStatus, TaskStep

__all__ = [
    "Agent", "AgentCapability", "AgentMetadata", "ToolUsingAgent",
    "AgentContext", "AgentResult", "Observation",
    "Task", "TaskStep", "TaskStatus", "StepStatus",
    "Planner", "Orchestrator", "get_default_orchestrator",
    "AgentRegistry", "get_default_agent_registry",
    "DeveloperAgent", "ResearchAgent", "BrowserAgent", "ComputerAgent",
    "FileDocumentAgent", "VerificationAgent", "register_all_agents",
    "RunAgentTaskTool", "register_agent_tools",
    "is_complex_request",
    "AgentError", "AgentNotFoundError", "AgentRegistrationError",
    "PlanningError", "InvalidPlanError", "OrchestrationError",
    "MaxStepsExceededError", "MaxDelegationsExceededError", "TaskCancelledError",
]
