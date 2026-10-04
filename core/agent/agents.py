"""
core.agent.agents — the initial specialized agents (Phase 4 spec, Part 14).

Each agent has a distinct capability boundary and tool set — no agent gets
every tool "because it exists" (Part 49). All inherit ToolUsingAgent
(core/agent/base.py) rather than reimplementing "pick a tool, call it
through the Tool Executor" logic five times.

Developer Agent note (spec Part 15/47): the valuable plan→write→run→
classify→fix loop already lives in `actions/dev_agent.py` (unchanged since
Phase 0) and is exposed as Phase 3's `dev_agent` Tool. DeveloperAgent here
is the *orchestration-layer* wrapper around that tool (plus `code_helper`)
— it does not reimplement dev_agent.py's internal loop, and it does not
import `actions.dev_agent` directly; it goes through the Tool Registry like
every other agent, per spec Part 15 ("must not directly bypass the
ToolExecutor").
"""
from __future__ import annotations

import logging

from core.llm.capabilities import ModelCapabilities
from core.tools.metadata import RiskLevel

from .base import AgentCapability, AgentMetadata, ToolUsingAgent
from .result import AgentResult
from .task import TaskStep

logger = logging.getLogger(__name__)


class DeveloperAgent(ToolUsingAgent):
    agent_id = "developer_agent"
    name = "Developer Agent"
    description = (
        "Handles coding tasks: writing, editing, running, and debugging code, "
        "and building multi-file projects. Wraps the existing dev_agent/code_helper "
        "tools' plan-write-run-fix behavior at the orchestration layer."
    )
    metadata = AgentMetadata(
        capabilities=(AgentCapability.CODING,),
        supported_task_types=("coding", "build_fix", "project_scaffold"),
        tool_names=("dev_agent", "code_helper"),
        model_requirements=ModelCapabilities(text_generation=True, tool_calling=True, reasoning=True),
        max_declared_risk=RiskLevel.CRITICAL,   # dev_agent tool is CRITICAL per Phase 0 audit
    )

    async def handle(self, step: TaskStep, context) -> AgentResult:
        """Retrieves project memory (architecture, known issues, tech
        stack, prior fixes — spec Part 31) before delegating to the
        standard ToolUsingAgent flow, and records a durable project fact on
        success. Both are best-effort: a missing/unavailable memory service
        never blocks the underlying coding work (spec Part 40)."""
        project_id = context.shared.get("project_id") if context and context.shared else None
        augmented_step = step

        if project_id and context.memory is not None:
            try:
                facts = context.memory.projects.get_facts(project_id)
                if facts:
                    context_text = "\n".join(f"- {f.summary or f.metadata.get('field', '')}: {f.content}"
                                              for f in facts[:10])
                    augmented_description = f"{step.description}\n\nKnown project context:\n{context_text}"
                    augmented_tool_args = step.tool_args
                    if step.tool_args and "description" in step.tool_args:
                        augmented_tool_args = {
                            **step.tool_args,
                            "description": f"{step.tool_args['description']}\n\nKnown project context:\n{context_text}",
                        }
                    augmented_step = TaskStep(
                        step_id=step.step_id, description=augmented_description,
                        status=step.status, required_capabilities=step.required_capabilities,
                        preferred_agent=step.preferred_agent, tool_name=step.tool_name,
                        tool_args=augmented_tool_args, dependencies=step.dependencies,
                        assigned_agent=step.assigned_agent,
                    )
            except Exception as exc:
                logger.warning("[DeveloperAgent] project memory retrieval failed (%s) — continuing without it.", exc)

        result = await super().handle(augmented_step, context)

        if result.success and project_id and context.memory is not None:
            try:
                context.memory.projects.set_fact(project_id, "last_dev_agent_outcome", result.summary[:500])
            except Exception as exc:
                logger.warning("[DeveloperAgent] failed to record project memory (%s).", exc)

        return result



class ResearchAgent(ToolUsingAgent):
    agent_id = "research_agent"
    name = "Research Agent"
    description = (
        "Handles research and information-gathering tasks: web search, weather, "
        "and flight lookups. Does not touch the filesystem, browser automation, "
        "or computer control."
    )
    metadata = AgentMetadata(
        capabilities=(AgentCapability.RESEARCH,),
        supported_task_types=("research", "information_lookup"),
        tool_names=("web_search", "weather_report", "flight_finder"),
        model_requirements=ModelCapabilities(text_generation=True, tool_calling=True),
        max_declared_risk=RiskLevel.LOW,
    )


class BrowserAgent(ToolUsingAgent):
    agent_id = "browser_agent"
    name = "Browser Agent"
    description = (
        "Handles browser-based interaction: navigation, search, clicking, form-filling. "
        "Uses the existing persistent browser_control tool/session — does not create a "
        "second browser controller."
    )
    metadata = AgentMetadata(
        capabilities=(AgentCapability.BROWSER_AUTOMATION,),
        supported_task_types=("browser_task", "web_interaction"),
        tool_names=("browser_control",),
        model_requirements=ModelCapabilities(text_generation=True, tool_calling=True),
        max_declared_risk=RiskLevel.HIGH,
    )


class ComputerAgent(ToolUsingAgent):
    agent_id = "computer_agent"
    name = "Computer Agent"
    description = (
        "Handles direct computer interaction: mouse/keyboard control, OS settings, "
        "screen/vision capture, and desktop automation (including the unsandboxed "
        "generated-code desktop_control tool — see Phase 0 audit; risk metadata "
        "reflects this, enforcement is Phase 6)."
    )
    metadata = AgentMetadata(
        capabilities=(AgentCapability.COMPUTER_CONTROL,),
        supported_task_types=("computer_task", "desktop_task"),
        tool_names=("computer_control", "computer_settings", "screen_process", "desktop_control"),
        model_requirements=ModelCapabilities(text_generation=True, tool_calling=True, vision=True),
        max_declared_risk=RiskLevel.CRITICAL,   # desktop_control tool is CRITICAL
    )


class FileDocumentAgent(ToolUsingAgent):
    agent_id = "file_document_agent"
    name = "File/Document Agent"
    description = (
        "Handles file management (list/create/delete/move/copy/rename) via file_controller, "
        "and document intelligence (summarize/extract/convert uploaded files) via "
        "file_processor. Distinguishes the two rather than treating all file operations "
        "the same way."
    )
    metadata = AgentMetadata(
        capabilities=(AgentCapability.FILE_MANAGEMENT, AgentCapability.DOCUMENT_INTELLIGENCE),
        supported_task_types=("file_management", "document_analysis"),
        tool_names=("file_controller", "file_processor"),
        model_requirements=ModelCapabilities(text_generation=True, tool_calling=True),
        max_declared_risk=RiskLevel.HIGH,
    )


class VerificationAgent(ToolUsingAgent):
    agent_id = "verification_agent"
    name = "Verification Agent"
    description = (
        "Determines whether a completed task actually satisfies its goal — e.g. running "
        "tests/builds via code_helper rather than trusting a prior step's self-report. "
        "Does not blindly approve; failure to verify is reported as such."
    )
    metadata = AgentMetadata(
        capabilities=(AgentCapability.VERIFICATION,),
        supported_task_types=("verification", "build_check"),
        tool_names=("code_helper", "system_status"),
        model_requirements=ModelCapabilities(text_generation=True, tool_calling=True),
        max_declared_risk=RiskLevel.HIGH,
    )


def register_all_agents(registry) -> None:
    for agent_cls in (DeveloperAgent, ResearchAgent, BrowserAgent, ComputerAgent,
                       FileDocumentAgent, VerificationAgent):
        registry.register(agent_cls())
