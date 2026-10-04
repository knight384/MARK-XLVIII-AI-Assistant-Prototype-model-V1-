"""
core.agent.context — AgentContext (Phase 4 spec, Part 5), distinct from
Phase 3's ToolContext (core/tools/base.py::ToolContext).

An AgentContext wraps a ToolContext-building capability plus references to
the Model Gateway and Tool Registry/Executor that agents use — it does NOT
expose raw provider SDK clients (spec: "Do not expose raw provider SDK
clients"), and it does not hold global mutable state — everything here is
scoped to one task's execution.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    task: Any = None                       # core.agent.task.Task, loosely typed to avoid an import cycle
    request_id: str | None = None
    config: Any = None                     # normally core.config.ConfigService
    model_gateway: Any = None              # core.llm.gateway.ModelGateway
    tool_registry: Any = None              # core.tools.registry.ToolRegistry
    tool_executor: Any = None              # core.tools.executor.ToolExecutor
    memory: Any = None                     # core.memory.service.MemoryService (Phase 5) — optional; None means "no memory available"
    logger: logging.Logger = field(default_factory=lambda: logger)
    cancellation_token: Any = None         # core.tools.base.CancellationToken (Phase 3's, reused per spec Part 27)
    parent_agent_id: str | None = None
    shared: dict[str, Any] = field(default_factory=dict)   # cross-step scratch space for one task's run

    def make_tool_context(self, extra: dict | None = None):
        """Builds a Phase 3 ToolContext from this AgentContext, so agents
        never construct one ad hoc with mismatched cancellation/logging."""
        from core.tools.base import ToolContext
        return ToolContext(
            request_id=self.request_id or (self.task.task_id if self.task else None) or "agent-task",
            task_id=self.task.task_id if self.task else None,
            config=self.config,
            cancellation_token=self.cancellation_token,
            logger=self.logger,
            extra=extra or {},
        )

    def retrieve_memory(self, query: str, memory_types: tuple = (), project_id: str | None = None,
                         limit: int = 5) -> list:
        """Safe, best-effort convenience wrapper: returns [] if no memory
        service is attached or retrieval fails (spec Part 40 — a memory
        failure must not crash an unrelated task)."""
        if self.memory is None:
            return []
        from core.memory.models import RetrievalQuery
        try:
            return self.memory.retrieve(RetrievalQuery(
                query=query, memory_types=memory_types, project_id=project_id, limit=limit,
            ))
        except Exception:
            self.logger.warning("AgentContext.retrieve_memory() failed — continuing without memory.")
            return []
