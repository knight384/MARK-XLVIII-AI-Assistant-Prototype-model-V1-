"""
core.agent.entrypoint — the bridge between the existing Tool Registry
(Phase 3) and the new Agent Runtime (Phase 4).

Design rationale (see docs/architecture/multi-agent-runtime.md for the full
writeup): Gemini Live only knows how to invoke declared tools. Rather than
restructure main.py's realtime audio loop to special-case "complex"
requests, this phase registers ONE additional tool — `run_agent_task` —
into the SAME Tool Registry the other 21 tools live in. Gemini itself
decides when to call it, exactly like every other tool (a request like
"open Chrome" never matches this tool's description; a request like
"research the best database, compare options, and prepare a recommendation"
does). This means:

  - main.py's `_execute_tool` needs ZERO special-casing — it already routes
    any tool name through the registry/executor uniformly.
  - The realtime voice path for simple commands is completely unaffected —
    no new model call, no new latency, no new code runs unless this
    specific tool is chosen.
  - The Orchestrator still only ever executes through the canonical
    ToolExecutor for every actual action (Tool -> Orchestrator -> Agents ->
    Tool Registry -> Tool Executor -> Tool), never a second execution path.

This module intentionally lives under core/agent/, not core/tools/, to
avoid a core.tools <-> core.agent import cycle (core.agent already imports
core.tools; core.tools must not import core.agent). It is registered into
the default Tool Registry via `register_agent_tools()`, called once from
main.py right after the Phase 3 registry/executor are constructed.
"""
from __future__ import annotations

import logging

from core.tools.base import Tool, ToolContext
from core.tools.metadata import Capability, RiskLevel, ToolCategory, ToolMetadata
from core.tools.results import ToolResult
from core.tools.schemas import ParamSchema, ToolSchema

logger = logging.getLogger(__name__)


class RunAgentTaskTool(Tool):
    name = "run_agent_task"
    description = (
        "Use this ONLY for complex, multi-step goals that clearly need several "
        "different capabilities in sequence — for example: researching something and "
        "then preparing a recommendation, analyzing a project and fixing a build error "
        "and then verifying it, or any goal explicitly involving multiple distinct "
        "stages. Do NOT use this for a single simple action (opening an app, one web "
        "search, one file operation, one computer-control command) — call the specific "
        "tool for that directly instead, it will be faster. This tool plans the goal "
        "into steps, delegates each step to a specialized agent (developer, research, "
        "browser, computer, file/document, or verification), and reports a structured "
        "summary of what succeeded and what failed."
    )
    schema = ToolSchema((
        ParamSchema("goal", "string",
                     "The complex, multi-step goal to accomplish, in the user's own words.",
                     required=True),
    ))
    metadata = ToolMetadata(
        category=ToolCategory.SYSTEM, risk_level=RiskLevel.MEDIUM,
        capabilities=(Capability.NETWORK,),
        timeout_seconds=300,  # orchestrated multi-step tasks legitimately take longer than a single tool call
        notes="Bridges into the Phase 4 Agent Runtime (core/agent/). Every actual action "
              "it triggers still executes through the same canonical ToolExecutor as every "
              "other tool — this tool does not bypass Tool Registry risk metadata.",
    )

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from .orchestrator import get_default_orchestrator
        from .task import TaskStatus

        goal = args.get("goal", "")
        if not goal:
            return ToolResult.fail(self.name, error="Missing 'goal'.", error_type="ToolValidationError")

        orchestrator = get_default_orchestrator()
        task = await orchestrator.run_task(
            goal, cancellation_token=context.cancellation_token, config=context.config,
        )

        lines = [task.summary()]
        for step in task.steps:
            marker = {"COMPLETED": "✓", "FAILED": "✗", "SKIPPED": "—", "CANCELLED": "×"}.get(step.status.value, "?")
            detail = step.result.summary if (step.result is not None and getattr(step.result, "summary", None)) else (step.error or "")
            lines.append(f"[{marker}] {step.description}" + (f" — {detail}" if detail else ""))
        message = "\n".join(lines)

        if task.status == TaskStatus.COMPLETED:
            return ToolResult.ok(self.name, data=message, metadata={"task_id": task.task_id, "status": task.status.value})
        return ToolResult(
            tool_name=self.name, success=False, data=message, message=message,
            error="; ".join(task.errors) if task.errors else "Task did not complete successfully.",
            error_type="TaskIncomplete",
            metadata={"task_id": task.task_id, "status": task.status.value},
        )


def register_agent_tools(tool_registry) -> None:
    """Adds the Agent Runtime's entry point to the existing Tool Registry.
    Idempotent-ish: if already registered (e.g. called twice), this will
    raise ToolRegistrationError, matching the registry's normal duplicate
    protection — callers should call this exactly once at startup."""
    if not tool_registry.exists(RunAgentTaskTool.name):
        tool_registry.register(RunAgentTaskTool())
