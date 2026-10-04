"""
core.agent.planner — the Planner (Phase 4 spec, Parts 9-11).

Converts a user goal into a structured plan (list of typed steps), using
the Phase 2 Model Gateway — never a provider SDK directly (spec Part 10).
Output is requested as JSON and structurally validated; invalid output
triggers a bounded, corrective retry (spec Part 11) — never an unbounded
loop.
"""
from __future__ import annotations

import json
import logging
import uuid

from core.agent.base import AgentCapability
from core.agent.errors import InvalidPlanError
from core.agent.task import Task, TaskStep
from core.llm.gateway import ModelGateway, get_default_gateway
from core.llm.types import Message, ModelRequest

logger = logging.getLogger(__name__)

_VALID_CAPABILITIES = {c.value for c in AgentCapability}

_PLANNER_SYSTEM = (
    "You are a task planner. Given a user goal, break it into a short sequence of "
    "concrete execution steps. Respond with ONLY a JSON object, no markdown, no "
    "explanation, matching this exact shape:\n"
    '{"goal": "<restated goal>", "steps": [\n'
    '  {"id": "step-1", "description": "<what to do>", '
    f'"required_capabilities": ["<one or more of: {", ".join(sorted(_VALID_CAPABILITIES))}>"], '
    '"dependencies": []}\n'
    "]}\n"
    "Keep the plan as short as possible — do not invent unnecessary steps. "
    "Each step's required_capabilities must be non-empty and drawn only from the listed values."
)


class Planner:
    def __init__(self, model_gateway: ModelGateway | None = None, max_attempts: int = 2):
        self._gateway = model_gateway or get_default_gateway()
        self._max_attempts = max_attempts

    async def plan(self, goal: str, memory_context: str = "") -> list[TaskStep]:
        """Returns a validated list of TaskStep. Raises InvalidPlanError if
        no valid plan could be produced within `max_attempts` (spec Part 11:
        bounded retries, never an infinite planning loop).

        `memory_context` (spec Part 30) is optional, pre-retrieved,
        already-bounded text (previous project decisions, user preferences,
        prior failures, etc.) — the Planner never reaches into
        memory/long_term.json or any store itself; the Orchestrator
        retrieves it through the MemoryService and passes it in."""
        last_error: str | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                raw = self._request_plan(goal, correction=last_error, memory_context=memory_context)
                return self._parse_and_validate(raw)
            except (json.JSONDecodeError, InvalidPlanError, KeyError, TypeError) as exc:
                last_error = str(exc)
                logger.warning("Planner attempt %d/%d failed: %s", attempt, self._max_attempts, last_error)

        raise InvalidPlanError(
            f"Planner could not produce a valid plan for goal '{goal}' after "
            f"{self._max_attempts} attempts. Last error: {last_error}"
        )

    def _request_plan(self, goal: str, correction: str | None, memory_context: str = "") -> str:
        prompt = f"Goal: {goal}"
        if memory_context:
            prompt += f"\n\nRelevant context from memory:\n{memory_context}"
        if correction:
            prompt += (
                f"\n\nYour previous response was invalid ({correction}). "
                f"Produce a corrected JSON plan following the required shape exactly."
            )
        request = ModelRequest(
            messages=[Message(role="user", content=prompt)],
            system_instruction=_PLANNER_SYSTEM,
        )
        response = self._gateway.generate(request, task_type="planner")
        return response.content

    def _parse_and_validate(self, raw_text: str) -> list[TaskStep]:
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)

        if "steps" not in data or not isinstance(data["steps"], list) or not data["steps"]:
            raise InvalidPlanError("Plan is missing a non-empty 'steps' list.")

        seen_ids: set[str] = set()
        steps: list[TaskStep] = []
        for i, raw_step in enumerate(data["steps"]):
            step_id = raw_step.get("id") or f"step-{i+1}-{uuid.uuid4().hex[:6]}"
            description = raw_step.get("description")
            if not description:
                raise InvalidPlanError(f"Step {i+1} is missing a 'description'.")
            if step_id in seen_ids:
                raise InvalidPlanError(f"Duplicate step id '{step_id}' in plan.")
            seen_ids.add(step_id)

            caps = tuple(raw_step.get("required_capabilities") or ())
            invalid_caps = [c for c in caps if c not in _VALID_CAPABILITIES]
            if invalid_caps:
                raise InvalidPlanError(f"Step '{step_id}' has unknown capabilities: {invalid_caps}")
            if not caps:
                raise InvalidPlanError(f"Step '{step_id}' has no required_capabilities.")

            deps = tuple(raw_step.get("dependencies") or ())

            steps.append(TaskStep(
                step_id=step_id, description=description,
                required_capabilities=caps, dependencies=deps,
                preferred_agent=raw_step.get("preferred_agent"),
                tool_name=raw_step.get("tool"), tool_args=raw_step.get("tool_args"),
            ))

        # Dependencies must reference real step ids in this same plan.
        for step in steps:
            unknown_deps = [d for d in step.dependencies if d not in seen_ids]
            if unknown_deps:
                raise InvalidPlanError(f"Step '{step.step_id}' depends on unknown step id(s): {unknown_deps}")

        return steps
