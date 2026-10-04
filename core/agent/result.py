"""core.agent.result — Observation and AgentResult models (Phase 4 spec, Parts 6, 21)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Observation:
    """A structured note the Orchestrator can consume, rather than relying
    exclusively on raw text (spec Part 21)."""
    source: Literal["tool", "agent", "system", "verification", "model"]
    type: str                 # e.g. "tool_result", "step_started", "plan_generated"
    content: str
    timestamp: float = field(default_factory=time.time)
    related_step: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Provider-neutral, structured result an Agent returns to the
    Orchestrator (spec Part 6). Deliberately structured, not a free-form
    natural-language handoff (Part 22: no free-form agent chat)."""
    success: bool
    status: str = "completed"          # "completed" | "failed" | "partial"
    summary: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)
    tool_results: list[Any] = field(default_factory=list)   # list[ToolResult]
    observations: list[Observation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, summary: str, tool_results: list | None = None,
           artifacts: dict | None = None, observations: list[Observation] | None = None) -> "AgentResult":
        return cls(success=True, status="completed", summary=summary,
                    tool_results=tool_results or [], artifacts=artifacts or {},
                    observations=observations or [])

    @classmethod
    def fail(cls, summary: str, errors: list[str] | None = None,
             tool_results: list | None = None) -> "AgentResult":
        return cls(success=False, status="failed", summary=summary,
                    errors=errors or [summary], tool_results=tool_results or [])
