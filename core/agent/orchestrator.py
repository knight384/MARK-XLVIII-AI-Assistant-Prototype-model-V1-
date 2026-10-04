"""
core.agent.orchestrator — the Orchestrator (Phase 4 spec, Part 12).

Owns: task creation, planning, agent selection, sequential step execution
(a simple dependency gate, not a full parallel scheduler — spec Part 8),
bounded retries, loop protection, cancellation propagation, and structured
partial-completion reporting. One central Orchestrator; agents never spawn
child agents or talk to each other directly (spec Part 22-23).
"""
from __future__ import annotations

import logging

from core.tools.base import CancellationToken

from .agents import register_all_agents
from .base import AgentCapability
from .context import AgentContext
from .errors import (
    AgentNotFoundError, InvalidPlanError, MaxDelegationsExceededError,
    MaxStepsExceededError, TaskCancelledError,
)
from .planner import Planner
from .registry import AgentRegistry, get_default_agent_registry
from .result import Observation
from .task import StepStatus, Task, TaskStep, TaskStatus

logger = logging.getLogger(__name__)

DEFAULT_MAX_PLAN_ATTEMPTS = 2      # matches Planner's default — kept here for visibility/config
DEFAULT_MAX_STEP_RETRIES = 2
DEFAULT_MAX_EXECUTION_STEPS = 20
DEFAULT_MAX_DELEGATIONS = 20


class Orchestrator:
    def __init__(
        self,
        agent_registry: AgentRegistry | None = None,
        tool_registry=None,
        tool_executor=None,
        model_gateway=None,
        planner: Planner | None = None,
        memory_service=None,
        max_step_retries: int = DEFAULT_MAX_STEP_RETRIES,
        max_execution_steps: int = DEFAULT_MAX_EXECUTION_STEPS,
        max_delegations: int = DEFAULT_MAX_DELEGATIONS,
    ):
        self._agent_registry = agent_registry or get_default_agent_registry()

        if tool_registry is None or tool_executor is None:
            from core.tools import ToolExecutor, get_default_registry as get_default_tool_registry
            tool_registry = tool_registry or get_default_tool_registry()
            tool_executor = tool_executor or ToolExecutor(tool_registry)
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor

        from core.llm.gateway import get_default_gateway
        self._model_gateway = model_gateway or get_default_gateway()
        self._planner = planner or Planner(model_gateway=self._model_gateway)

        if memory_service is None:
            from core.memory import get_default_memory_service
            memory_service = get_default_memory_service()
        self._memory_service = memory_service

        self._max_step_retries = max_step_retries
        self._max_execution_steps = max_execution_steps
        self._max_delegations = max_delegations

    async def run_task(self, goal: str, cancellation_token: CancellationToken | None = None,
                        config=None) -> Task:
        """The main entry point: goal in, a fully-executed (or
        failed/cancelled) Task out. Never raises for ordinary planning/
        execution failures — those are represented in the returned Task's
        status/steps/errors (spec Part 26: partial completion must be
        visible, not hidden behind an exception)."""
        task = Task(goal=goal)
        cancellation_token = cancellation_token or CancellationToken()
        try:
            return await self._run_task_impl(task, goal, cancellation_token, config)
        except Exception as e:
            logger.exception("[Orchestrator] Uncaught exception during task execution")
            task.set_status(TaskStatus.FAILED)
            task.errors.append(f"Uncaught orchestration exception: {e}")
            from core.runtime.events import get_default_bus, RuntimeEvent, EventPriority
            get_default_bus().publish(RuntimeEvent(
                event_type="task_crashed",
                payload={"task_id": task.task_id, "error": str(e)},
                priority=EventPriority.HIGH
            ))
            return task

    async def _run_task_impl(self, task: Task, goal: str, cancellation_token: CancellationToken,
                        config=None) -> Task:
        task.observations.append(Observation(source="system", type="task_created", content=goal))
        logger.info("[Orchestrator] Task created: %s (id=%s)", goal, task.task_id)

        if cancellation_token.is_cancelled:
            task.set_status(TaskStatus.CANCELLED)
            return task

        task.set_status(TaskStatus.PLANNING)
        relevant_memory_text = self._retrieve_planning_context(goal)
        try:
            steps = await self._planner.plan(goal, memory_context=relevant_memory_text)
        except InvalidPlanError as exc:
            task.set_status(TaskStatus.FAILED)
            task.errors.append(str(exc))
            task.observations.append(Observation(source="system", type="planning_failed", content=str(exc)))
            logger.error("[Orchestrator] Planning failed for task %s: %s", task.task_id, exc)
            return task

        if len(steps) > self._max_execution_steps:
            task.set_status(TaskStatus.FAILED)
            err = (f"Plan has {len(steps)} steps, exceeding max_execution_steps="
                   f"{self._max_execution_steps} (loop protection).")
            task.errors.append(err)
            logger.error("[Orchestrator] %s", err)
            return task

        task.steps = steps
        task.observations.append(Observation(
            source="system", type="plan_generated",
            content=f"Plan with {len(steps)} step(s) generated.",
            metadata={"step_ids": [s.step_id for s in steps]},
        ))
        logger.info("[Orchestrator] Plan generated for task %s: %d step(s)", task.task_id, len(steps))

        task.set_status(TaskStatus.RUNNING)
        delegations = 0

        # Simple sequential execution respecting the dependency gate — not a
        # parallel DAG scheduler (spec Part 8). Loops until every step is in
        # a terminal state or loop-protection/cancellation stops us.
        remaining = {s.step_id: s for s in task.steps}
        executed_this_pass_guard = 0
        max_passes = len(task.steps) + 2  # generous bound: prevents an unsatisfiable-dependency deadlock spin

        passes = 0
        while remaining and passes < max_passes:
            passes += 1
            made_progress = False

            for step_id in list(remaining.keys()):
                if cancellation_token.is_cancelled:
                    task.set_status(TaskStatus.CANCELLED)
                    for s in remaining.values():
                        s.status = StepStatus.CANCELLED
                    logger.info("[Orchestrator] Task %s cancelled.", task.task_id)
                    return task

                step = remaining[step_id]
                if not step.is_ready(task.completed_step_ids(), task.failed_step_ids()):
                    continue

                if step_id in [s.step_id for s in task.steps if s.status == StepStatus.SKIPPED]:
                    continue

                # A dependency failed — this step can never run.
                if any(dep in task.failed_step_ids() for dep in step.dependencies):
                    step.status = StepStatus.SKIPPED
                    step.error = "Skipped: a dependency step failed."
                    del remaining[step_id]
                    made_progress = True
                    continue

                delegations += 1
                if delegations > self._max_delegations:
                    task.set_status(TaskStatus.FAILED)
                    task.errors.append(
                        f"Exceeded max_delegations={self._max_delegations} (loop protection)."
                    )
                    logger.error("[Orchestrator] Task %s: %s", task.task_id, task.errors[-1])
                    return task

                await self._execute_step(task, step, cancellation_token, config)
                del remaining[step_id]
                made_progress = True

            if not made_progress:
                break  # remaining steps have unsatisfiable dependencies — stop, report as failed below

        for step_id, step in remaining.items():
            step.status = StepStatus.SKIPPED
            step.error = "Skipped: unresolved dependency (loop protection stopped the scheduler)."

        task.set_status(TaskStatus.COMPLETED if task.is_fully_successful() else TaskStatus.FAILED)
        task.observations.append(Observation(
            source="system", type="task_finished", content=task.summary(),
        ))
        self._record_task_outcome(task)
        logger.info("[Orchestrator] %s", task.summary())
        return task

    def _retrieve_planning_context(self, goal: str) -> str:
        """Bounded, best-effort memory retrieval before planning (spec Part
        29/30) — never mandatory, never crashes the task if it fails
        (Part 40), and never injects the entire memory store (Part 35)."""
        if self._memory_service is None:
            return ""
        try:
            from core.memory.models import RetrievalQuery
            results = self._memory_service.retrieve(RetrievalQuery(query=goal, limit=5))
        except Exception as exc:
            logger.warning("[Orchestrator] Planning memory retrieval failed (%s) — planning without it.", exc)
            return ""
        if not results:
            return ""
        lines = [r.record.content for r in results]
        text = "\n".join(f"- {line}" for line in lines)
        max_chars = getattr(self._memory_service.config, "max_context_chars", 2000)
        return text[:max_chars]

    def _record_task_outcome(self, task: Task) -> None:
        """Writes a meaningful episodic event on task completion/failure
        (spec Part 13 trigger: 'task completed' / 'task failed') — not
        every step, not raw logs. Best-effort; a memory write failure must
        not affect the already-computed task result (spec Part 40)."""
        if self._memory_service is None:
            return
        try:
            self._memory_service.episodic.record_event(
                f"Task {'completed' if task.status == TaskStatus.COMPLETED else 'failed'}: {task.goal}",
                result=task.summary(), related_task=task.task_id,
                importance=0.7 if task.status == TaskStatus.COMPLETED else 0.6,
            )
        except Exception as exc:
            logger.warning("[Orchestrator] Failed to record episodic task outcome (%s).", exc)

    async def _execute_step(self, task: Task, step: TaskStep, cancellation_token: CancellationToken,
                             config) -> None:
        step.status = StepStatus.RUNNING
        task.observations.append(Observation(
            source="system", type="step_started", content=step.description, related_step=step.step_id,
        ))

        agent = self._select_agent(step)
        if agent is None:
            step.status = StepStatus.FAILED
            step.error = f"No registered agent covers capabilities {step.required_capabilities}."
            task.errors.append(step.error)
            logger.error("[Orchestrator] Task %s step %s: %s", task.task_id, step.step_id, step.error)
            return

        step.assigned_agent = agent.agent_id
        context = AgentContext(
            task=task, request_id=task.task_id, config=config,
            model_gateway=self._model_gateway, tool_registry=self._tool_registry,
            tool_executor=self._tool_executor, memory=self._memory_service,
            cancellation_token=cancellation_token,
        )

        last_error: str | None = None
        for attempt in range(1, self._max_step_retries + 1):
            step.attempts = attempt
            try:
                result = await agent.handle(step, context)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("[Orchestrator] Step '%s' attempt %d/%d raised: %s",
                                step.step_id, attempt, self._max_step_retries, last_error)
                continue

            step.result = result
            task.observations.extend(result.observations)
            if result.success:
                step.status = StepStatus.COMPLETED
                task.observations.append(Observation(
                    source="agent", type="step_completed", content=result.summary,
                    related_step=step.step_id, metadata={"agent_id": agent.agent_id},
                ))
                return
            last_error = result.summary or "; ".join(result.errors) or "unknown agent failure"
            logger.warning("[Orchestrator] Step '%s' attempt %d/%d failed: %s",
                            step.step_id, attempt, self._max_step_retries, last_error)

        step.status = StepStatus.FAILED
        step.error = last_error or "unknown failure"
        task.errors.append(f"Step '{step.step_id}' ({agent.agent_id}): {step.error}")
        task.observations.append(Observation(
            source="agent", type="step_failed", content=step.error,
            related_step=step.step_id, metadata={"agent_id": agent.agent_id},
        ))

    def _select_agent(self, step: TaskStep):
        """Deterministic capability match (spec Part 13: 'Do not use an LLM
        to decide agent selection if a deterministic capability match is
        sufficient.')."""
        if step.preferred_agent:
            agent = self._agent_registry.get(step.preferred_agent)
            if agent is not None:
                return agent
            logger.warning("Preferred agent '%s' not found — falling back to capability match.",
                            step.preferred_agent)

        for cap_name in step.required_capabilities:
            try:
                capability = AgentCapability(cap_name)
            except ValueError:
                continue
            candidates = self._agent_registry.find_by_capability(capability)
            if candidates:
                return candidates[0]
        return None


_default_orchestrator: Orchestrator | None = None


def get_default_orchestrator() -> Orchestrator:
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = Orchestrator()
    return _default_orchestrator
