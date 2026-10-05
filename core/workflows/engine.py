import logging
import time
import uuid
from typing import Optional

from core.tools.base import CancellationToken
from .models import (
    WorkflowDefinition, WorkflowState, WorkflowRun, WorkflowRunStatus, WorkflowNode
)
from .store import WorkflowStore, get_default_store

logger = logging.getLogger(__name__)

class WorkflowEngine:
    def __init__(self, store: WorkflowStore | None = None):
        self.store = store or get_default_store()

    def register_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Validate and persist a workflow definition."""
        self._validate_definition(definition)
        self.store.save_definition(definition)
        logger.info(f"[WorkflowEngine] Registered workflow definition '{definition.name}' (id={definition.id}, v={definition.version})")
        return definition

    def _validate_definition(self, definition: WorkflowDefinition):
        if not definition.nodes:
            raise ValueError("Workflow definition must have at least one node")
        if definition.start_node_id not in definition.nodes:
            raise ValueError(f"Start node {definition.start_node_id} not found in nodes")
            
        # Check edges
        for node_id, node in definition.nodes.items():
            for next_node in node.next_nodes:
                if next_node not in definition.nodes:
                    raise ValueError(f"Node {node_id} references unknown next node {next_node}")

    def activate(self, definition_id: str) -> None:
        defn = self.store.get_definition(definition_id)
        if not defn:
            raise ValueError("Definition not found")
        defn.state = WorkflowState.ACTIVE
        defn.updated_at = time.time()
        self.store.save_definition(defn)

    def deactivate(self, definition_id: str) -> None:
        defn = self.store.get_definition(definition_id)
        if not defn:
            raise ValueError("Definition not found")
        defn.state = WorkflowState.PAUSED
        defn.updated_at = time.time()
        self.store.save_definition(defn)

    def start_run(self, definition_id: str, context: dict | None = None, mission_id: str | None = None, correlation_id: str | None = None) -> WorkflowRun:
        """Start a new execution run of a workflow."""
        defn = self.store.get_definition(definition_id)
        if not defn:
            raise ValueError("Definition not found")
        if defn.state != WorkflowState.ACTIVE:
            raise ValueError("Cannot start run for inactive workflow")
            
        run = WorkflowRun(
            id=str(uuid.uuid4()),
            workflow_id=defn.id,
            workflow_version=defn.version,
            mission_id=mission_id,
            status=WorkflowRunStatus.QUEUED,
            current_node_id=defn.start_node_id,
            context=context or {},
            correlation_id=correlation_id or str(uuid.uuid4())
        )
        self.store.save_run(run)
        
        # Emit event
        from core.runtime.events import get_default_bus, RuntimeEvent
        get_default_bus().publish(RuntimeEvent(
            event_type="workflow.started",
            payload={"run_id": run.id, "workflow_id": run.workflow_id}
        ))
        
        return run

    def cancel_run(self, run_id: str) -> None:
        """Cooperative cancellation."""
        run = self.store.get_run(run_id)
        if not run:
            raise ValueError("Run not found")
        
        if run.status in (WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED, WorkflowRunStatus.TIMED_OUT):
            return # Already terminal
            
        run.status = WorkflowRunStatus.CANCELLING
        run.updated_at = time.time()
        self.store.save_run(run)
        
        from core.runtime.events import get_default_bus, RuntimeEvent
        get_default_bus().publish(RuntimeEvent(
            event_type="workflow.cancel_requested",
            payload={"run_id": run.id}
        ))
        logger.info(f"[WorkflowEngine] Cancel requested for run {run.id}")

_default_engine: WorkflowEngine | None = None

def get_default_engine() -> WorkflowEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = WorkflowEngine()
    return _default_engine
