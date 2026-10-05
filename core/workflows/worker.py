import asyncio
import logging
import time
import uuid
from typing import Optional

from core.tools.base import CancellationToken
from .models import WorkflowRun, WorkflowRunStatus, StepType, WorkflowStepRun
from .store import WorkflowStore, get_default_store
from .engine import WorkflowEngine, get_default_engine
from .effects import EffectBoundary, get_default_effect_boundary
from .conditions import evaluate_condition
from core.runtime.events import get_default_bus, RuntimeEvent

logger = logging.getLogger(__name__)

class WorkflowWorker:
    def __init__(
        self,
        store: WorkflowStore | None = None,
        engine: WorkflowEngine | None = None,
        effect_boundary: EffectBoundary | None = None,
        poll_interval_sec: float = 2.0
    ):
        self.store = store or get_default_store()
        self.engine = engine or get_default_engine()
        self.effect_boundary = effect_boundary or get_default_effect_boundary()
        self.poll_interval_sec = poll_interval_sec
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[WorkflowWorker] Started background processing loop.")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[WorkflowWorker] Stopped gracefully.")

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"[WorkflowWorker] Unexpected error in loop: {e}")
            await asyncio.sleep(self.poll_interval_sec)

    async def _tick(self):
        now = time.time()
        
        # In a multi-worker setup, we would do an atomic SELECT FOR UPDATE or UPDATE ... WHERE locked_until < now
        # For SQLite in-process, we use the threading lock in store.
        
        # Fetch runs that need attention
        # 1. QUEUED
        # 2. RUNNING but lock expired (crash recovery)
        # 3. WAITING_APPROVAL (check if resolved)
        # 4. CANCELLING
        
        runs = []
        with self.store._lock:
            # Coarse fetch and filter
            all_runs = self.store._conn.execute(
                "SELECT * FROM workflow_runs WHERE status IN ('QUEUED', 'RUNNING', 'WAITING_APPROVAL', 'CANCELLING', 'RETRYING')"
            ).fetchall()
            
            for row in all_runs:
                run = self.store._row_to_run(row)
                if run.status == WorkflowRunStatus.RUNNING and run.locked_until and run.locked_until > now:
                    continue # currently locked by an active worker task
                
                # claim lock
                run.locked_until = now + 60.0 # lock for 60s
                self.store._conn.execute("UPDATE workflow_runs SET locked_until = ? WHERE id = ?", (run.locked_until, run.id))
                runs.append(run)
            self.store._conn.commit()

        for run in runs:
            asyncio.create_task(self._process_run(run.id))

    async def _process_run(self, run_id: str):
        # We process step by step until we hit a wait state (e.g. tool execution wait, approval)
        # We will hold the lock by refreshing it, or just executing.
        run = self.store.get_run(run_id)
        if not run:
            return

        if run.status == WorkflowRunStatus.CANCELLING:
            run.status = WorkflowRunStatus.CANCELLED
            run.finished_at = time.time()
            self.store.save_run(run)
            get_default_bus().publish(RuntimeEvent(event_type="workflow.cancelled", payload={"run_id": run.id}))
            return

        defn = self.store.get_definition(run.workflow_id)
        if not defn:
            run.status = WorkflowRunStatus.FAILED
            run.error = "Workflow definition not found"
            run.finished_at = time.time()
            self.store.save_run(run)
            return

        if run.status in (WorkflowRunStatus.QUEUED, WorkflowRunStatus.RETRYING):
            run.status = WorkflowRunStatus.RUNNING
            if not run.started_at:
                run.started_at = time.time()
            self.store.save_run(run)

        # Execution loop
        while True:
            # Check for cancellation
            run = self.store.get_run(run.id)
            if run.status == WorkflowRunStatus.CANCELLING:
                run.status = WorkflowRunStatus.CANCELLED
                run.finished_at = time.time()
                self.store.save_run(run)
                get_default_bus().publish(RuntimeEvent(event_type="workflow.cancelled", payload={"run_id": run.id}))
                return

            if not run.current_node_id:
                # Workflow finished successfully
                run.status = WorkflowRunStatus.SUCCEEDED
                run.finished_at = time.time()
                self.store.save_run(run)
                get_default_bus().publish(RuntimeEvent(event_type="workflow.completed", payload={"run_id": run.id}))
                return

            node = defn.nodes.get(run.current_node_id)
            if not node:
                run.status = WorkflowRunStatus.FAILED
                run.error = f"Node {run.current_node_id} not found"
                run.finished_at = time.time()
                self.store.save_run(run)
                get_default_bus().publish(RuntimeEvent(event_type="workflow.failed", payload={"run_id": run.id, "error": run.error}))
                return
            
            # Step execution
            step_id = str(uuid.uuid4())
            step_run = WorkflowStepRun(
                id=step_id, run_id=run.id, node_id=node.id,
                status=WorkflowRunStatus.RUNNING, started_at=time.time()
            )
            self.store.save_step_run(step_run)
            get_default_bus().publish(RuntimeEvent(event_type="workflow.step.started", payload={"run_id": run.id, "step_id": step_id, "node_id": node.id}))
            
            try:
                # Renew lock
                run.locked_until = time.time() + 300.0
                self.store.save_run(run)
                
                # Execute node logic
                next_node_id = await self._execute_node(run, step_run, node)
                
                step_run.status = WorkflowRunStatus.SUCCEEDED
                step_run.finished_at = time.time()
                self.store.save_step_run(step_run)
                get_default_bus().publish(RuntimeEvent(event_type="workflow.step.completed", payload={"run_id": run.id, "step_id": step_id, "node_id": node.id}))
                
                # Transition
                run.current_node_id = next_node_id
                self.store.save_run(run)
                
            except Exception as e:
                # Determine if it's an approval wait
                from core.policy.errors import ApprovalDeniedError
                if type(e).__name__ == "ApprovalRequired":
                    # Actually, ToolExecutor resolves approval internally. If it fails, it returns a failed ToolResult.
                    # We shouldn't get an ApprovalRequired exception from ToolExecutor.execute() unless it was unhandled.
                    pass
                
                logger.exception(f"Step {node.id} failed in run {run.id}")
                step_run.status = WorkflowRunStatus.FAILED
                step_run.error = str(e)
                step_run.finished_at = time.time()
                self.store.save_step_run(step_run)
                get_default_bus().publish(RuntimeEvent(event_type="workflow.step.failed", payload={"run_id": run.id, "step_id": step_id, "node_id": node.id, "error": str(e)}))
                
                run.attempt += 1
                if run.attempt <= run.max_attempts:
                    run.status = WorkflowRunStatus.RETRYING
                    run.error = f"Step {node.id} failed: {e}"
                    # Backoff
                    backoff = (2 ** run.attempt) * 5
                    run.locked_until = time.time() + backoff
                    self.store.save_run(run)
                    get_default_bus().publish(RuntimeEvent(event_type="workflow.retrying", payload={"run_id": run.id, "attempt": run.attempt, "backoff": backoff}))
                    return
                else:
                    run.status = WorkflowRunStatus.FAILED
                    run.error = f"Step {node.id} permanently failed: {e}"
                    run.finished_at = time.time()
                    self.store.save_run(run)
                    get_default_bus().publish(RuntimeEvent(event_type="workflow.failed", payload={"run_id": run.id, "error": run.error}))
                    return

    async def _execute_node(self, run: WorkflowRun, step_run: WorkflowStepRun, node) -> Optional[str]:
        # cancellation token for tool/agent
        c_token = CancellationToken()
        # In a full implementation, the cancelling status would flip this token.
        
        if node.type == StepType.AGENT:
            goal = node.config.get("goal", "")
            # Inject context variables into goal
            formatted_goal = goal.format(**run.context) if goal else ""
            step_run.inputs = {"goal": formatted_goal}
            
            task = await self.effect_boundary.execute_agent_task(formatted_goal, run.id, step_run.id, c_token)
            
            step_run.outputs = {"task_id": task.task_id, "status": task.status.value, "summary": task.summary()}
            if task.status.value == "FAILED":
                raise RuntimeError(f"Agent task failed: {task.summary()}")
                
        elif node.type == StepType.TOOL:
            tool_name = node.config.get("tool_name", "")
            args_template = node.config.get("args", {})
            # Very basic string interpolation for args
            args = {}
            for k, v in args_template.items():
                if isinstance(v, str):
                    try:
                        args[k] = v.format(**run.context)
                    except KeyError:
                        args[k] = v
                else:
                    args[k] = v
            
            step_run.inputs = {"tool_name": tool_name, "args": args}
            result = await self.effect_boundary.execute_tool(tool_name, args, run.id, step_run.id, c_token)
            
            step_run.outputs = {"success": result.success, "message": result.message, "error": result.error}
            
            if not result.success:
                raise RuntimeError(f"Tool execution failed: {result.error}")
            
            # Save result to context
            result_key = node.config.get("result_key")
            if result_key:
                run.context[result_key] = result.message
                
        elif node.type == StepType.CONDITION:
            expression = node.config.get("expression", "")
            true_node = node.config.get("true_node")
            false_node = node.config.get("false_node")
            
            step_run.inputs = {"expression": expression}
            
            is_true = evaluate_condition(expression, run.context)
            step_run.outputs = {"result": is_true}
            
            return true_node if is_true else false_node
            
        elif node.type == StepType.NOTIFICATION:
            # Minimal notification logic
            msg = node.config.get("message", "").format(**run.context)
            try:
                from core.notifications import get_default_notification_service
                get_default_notification_service().notify(msg)
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
            step_run.outputs = {"notified": True}

        # default sequential transition
        if node.next_nodes:
            return node.next_nodes[0]
        return None

