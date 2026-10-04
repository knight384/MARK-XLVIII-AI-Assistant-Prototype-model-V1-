"""
core.agent.task — lightweight execution Task/TaskStep model (Phase 4 spec,
Parts 6-7-8).

This represents an operation currently being executed, not a persistent
long-term Mission — no database, no cross-process persistence. In-memory
state, owned entirely by the Orchestrator that created it (spec Part 36:
"Keep Phase 4 task state in one place... The Agent Runtime owns execution
state."). A future Phase 9 Mission system can build persistence on top of
this without changing its shape.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


@dataclass
class TaskStep:
    step_id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    required_capabilities: tuple[str, ...] = ()
    preferred_agent: str | None = None
    # Optional explicit tool routing (planner-supplied or caller-supplied) —
    # when present, the assigned agent uses it directly instead of asking
    # the model to choose a tool (see core/agent/base.py::ToolUsingAgent).
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    dependencies: tuple[str, ...] = ()
    assigned_agent: str | None = None
    result: Any = None            # an AgentResult, once completed (loosely typed to avoid an import cycle)
    error: str | None = None
    attempts: int = 0

    def is_ready(self, completed_step_ids: set[str], failed_step_ids: set[str]) -> bool:
        """Simple dependency gate — not a full DAG scheduler (spec Part 8:
        'Do not create a sophisticated workflow engine yet'). A step is
        ready once every dependency has completed; it's permanently
        unreachable if any dependency failed."""
        if any(dep in failed_step_ids for dep in self.dependencies):
            return False
        return all(dep in completed_step_ids for dep in self.dependencies)


@dataclass
class Task:
    goal: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: TaskStatus = TaskStatus.CREATED
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    parent_task_id: str | None = None
    current_step_index: int = 0
    steps: list[TaskStep] = field(default_factory=list)
    observations: list[Any] = field(default_factory=list)   # list[Observation], see result.py
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_status(self, status: TaskStatus) -> None:
        self.status = status
        self.updated_at = time.time()

    def completed_step_ids(self) -> set[str]:
        return {s.step_id for s in self.steps if s.status == StepStatus.COMPLETED}

    def failed_step_ids(self) -> set[str]:
        return {s.step_id for s in self.steps if s.status == StepStatus.FAILED}

    def is_fully_successful(self) -> bool:
        return bool(self.steps) and all(s.status == StepStatus.COMPLETED for s in self.steps)

    def summary(self) -> str:
        counts: dict[str, int] = {}
        for s in self.steps:
            counts[s.status.value] = counts.get(s.status.value, 0) + 1
        parts = ", ".join(f"{v} {k.lower()}" for k, v in counts.items())
        return f"Task '{self.goal}' [{self.status.value}]: {parts or 'no steps'}"
