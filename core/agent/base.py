"""
core.agent.base — the standard Agent interface (Phase 4 spec, Part 3) and a
shared ToolUsingAgent helper implementing the common
"decide which registered tool to call, then call it through the Tool
Executor" pattern so specialized agents don't duplicate that logic
(spec Part 49: avoid "agent theater" — one real capability boundary per
agent, not five near-identical reimplementations).
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from core.llm.capabilities import ModelCapabilities
from core.tools.metadata import RiskLevel

from .context import AgentContext
from .errors import AgentError
from .result import AgentResult, Observation
from .task import TaskStep

logger = logging.getLogger(__name__)


class AgentCapability(str, Enum):
    CODING = "coding"
    RESEARCH = "research"
    BROWSER_AUTOMATION = "browser_automation"
    COMPUTER_CONTROL = "computer_control"
    FILE_MANAGEMENT = "file_management"
    DOCUMENT_INTELLIGENCE = "document_intelligence"
    VERIFICATION = "verification"


@dataclass(frozen=True)
class AgentMetadata:
    capabilities: tuple[AgentCapability, ...]
    supported_task_types: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()               # the ONLY tools this agent may call
    model_requirements: ModelCapabilities = field(default_factory=lambda: ModelCapabilities(text_generation=True))
    max_declared_risk: RiskLevel = RiskLevel.LOW    # metadata only — not enforced (Phase 6 will enforce)
    health: str = "healthy"


class Agent(ABC):
    agent_id: str
    name: str
    description: str
    metadata: AgentMetadata

    @abstractmethod
    async def handle(self, step: TaskStep, context: AgentContext) -> AgentResult:
        raise NotImplementedError


class ToolUsingAgent(Agent):
    """Shared implementation for agents whose job is "run one of my
    declared tools to accomplish this step." Two paths:

    1. **Explicit routing** — if `step.tool_name` is already set (by the
       Planner's structured output, or by a caller constructing steps
       directly, as most tests do for determinism), call it directly with
       `step.tool_args or {}`.
    2. **Model-assisted routing** — otherwise, ask the Model Gateway (never
       a provider SDK directly — spec Part 35) to choose one of this
       agent's declared tools and produce arguments for the step
       description, as structured JSON.

    Either way, execution always goes through `context.tool_executor`
    (Phase 3's canonical ToolExecutor) — never a second executor, never a
    direct `actions.*` import (spec Parts 3, 34).
    """

    async def handle(self, step: TaskStep, context: AgentContext) -> AgentResult:
        if context.cancellation_token is not None and context.cancellation_token.is_cancelled:
            return AgentResult.fail(f"{self.agent_id}: cancelled before starting step '{step.step_id}'.")

        tool_name = step.tool_name
        tool_args = step.tool_args or {}

        if not tool_name:
            try:
                tool_name, tool_args = await self._decide_tool_call(step, context)
            except Exception as exc:
                logger.warning("%s: model-assisted tool selection failed for step '%s': %s",
                                self.agent_id, step.step_id, exc)
                return AgentResult.fail(f"{self.agent_id} could not decide which tool to use: {exc}")

        if tool_name not in self.metadata.tool_names:
            return AgentResult.fail(
                f"{self.agent_id}: tool '{tool_name}' is outside this agent's declared tool set "
                f"{self.metadata.tool_names}."
            )

        tool_context = context.make_tool_context(extra=context.shared.get("tool_context_extra", {}))
        tool_result = await context.tool_executor.execute(tool_name, tool_args, tool_context)

        observation = Observation(
            source="tool", type="tool_result",
            content=tool_result.as_model_text(), related_step=step.step_id,
            metadata={"tool_name": tool_name, "success": tool_result.success},
        )

        if tool_result.success:
            return AgentResult.ok(
                summary=tool_result.as_model_text(),
                tool_results=[tool_result], observations=[observation],
            )
        return AgentResult(
            success=False, status="failed", summary=tool_result.as_model_text(),
            tool_results=[tool_result], observations=[observation],
            errors=[tool_result.error or tool_result.as_model_text()],
        )

    async def _decide_tool_call(self, step: TaskStep, context: AgentContext) -> tuple[str, dict]:
        """Asks the Model Gateway to pick one of this agent's declared
        tools and produce JSON arguments for the step. Never calls a
        provider SDK directly — only `context.model_gateway.generate()`."""
        from core.llm.types import Message, ModelRequest

        tool_descriptions = []
        for name in self.metadata.tool_names:
            tool = context.tool_registry.get(name)
            if tool is not None:
                tool_descriptions.append(f"- {tool.name}: {tool.description}")

        prompt = (
            f"You are the {self.name}. Task step: \"{step.description}\"\n\n"
            f"Available tools:\n" + "\n".join(tool_descriptions) + "\n\n"
            f"Respond with ONLY a JSON object: "
            f'{{"tool": "<one of the tool names above>", "arguments": {{...}}}}. '
            f"No markdown, no explanation."
        )
        request = ModelRequest(messages=[Message(role="user", content=prompt)])
        response = context.model_gateway.generate(request, task_type="planner")

        text = response.content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text)
        tool_name = parsed.get("tool")
        tool_args = parsed.get("arguments", {}) or {}
        if not tool_name:
            raise AgentError(f"Model did not select a tool for step '{step.step_id}'.", agent_id=self.agent_id)
        return tool_name, tool_args
