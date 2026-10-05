import logging
from typing import Any, Dict

from core.tools.base import ToolContext, CancellationToken
from core.tools.executor import ToolExecutor
from core.tools.results import ToolResult
from core.agent.orchestrator import get_default_orchestrator
from core.agent.task import Task

logger = logging.getLogger(__name__)

class EffectBoundary:
    """
    Enforces the single authorization boundary for Workflows.
    No workflow step may bypass ToolExecutor or the Orchestrator.
    """
    def __init__(self, tool_executor: ToolExecutor | None = None):
        self._tool_executor = tool_executor

    def _get_tool_executor(self) -> ToolExecutor:
        if self._tool_executor is None:
            from core.tools import get_default_registry
            from core.tools.executor import ToolExecutor
            self._tool_executor = ToolExecutor(get_default_registry())
        return self._tool_executor

    async def execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        run_id: str,
        step_id: str,
        cancellation_token: CancellationToken | None = None
    ) -> ToolResult:
        """Execute a tool strictly through the authoritative ToolExecutor."""
        executor = self._get_tool_executor()
        ctx = ToolContext(
            task_id=f"workflow_{run_id}",
            request_id=step_id,
            agent_id="system_workflow",
            source="workflow",
            session_id=run_id,
            cancellation_token=cancellation_token
        )
        logger.info(f"[EffectBoundary] Executing tool {tool_name} for workflow step {step_id}")
        return await executor.execute(tool_name, args, ctx)

    async def execute_agent_task(
        self,
        goal: str,
        run_id: str,
        step_id: str,
        cancellation_token: CancellationToken | None = None
    ) -> Task:
        """Execute an agent task strictly through the authoritative Orchestrator."""
        orchestrator = get_default_orchestrator()
        logger.info(f"[EffectBoundary] Executing agent task for workflow step {step_id}")
        return await orchestrator.run_task(
            goal=goal,
            cancellation_token=cancellation_token
        )

_default_effect_boundary: EffectBoundary | None = None

def get_default_effect_boundary() -> EffectBoundary:
    global _default_effect_boundary
    if _default_effect_boundary is None:
        _default_effect_boundary = EffectBoundary()
    return _default_effect_boundary
