import sqlite3
import threading
import json
from pathlib import Path
from typing import Optional, List

from .models import (
    WorkflowDefinition, WorkflowState, WorkflowNode, StepType,
    WorkflowRun, WorkflowRunStatus, WorkflowStepRun
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_definitions (
    id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    nodes TEXT NOT NULL,
    start_node_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    workflow_version INTEGER NOT NULL,
    mission_id TEXT,
    status TEXT NOT NULL,
    current_node_id TEXT,
    context TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    error TEXT,
    attempt INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    locked_until REAL
);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);

CREATE TABLE IF NOT EXISTS workflow_step_runs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    status TEXT NOT NULL,
    inputs TEXT NOT NULL,
    outputs TEXT NOT NULL,
    error TEXT,
    started_at REAL,
    finished_at REAL,
    attempt INTEGER NOT NULL,
    FOREIGN KEY(run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workflow_step_runs_run ON workflow_step_runs(run_id);
"""

class WorkflowStore:
    def __init__(self, db_path: Path):
        self._path = db_path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.executescript("PRAGMA foreign_keys = ON;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save_definition(self, definition: WorkflowDefinition) -> None:
        nodes_dict = {
            n_id: {
                "id": n.id,
                "type": n.type.value,
                "name": n.name,
                "config": n.config,
                "next_nodes": n.next_nodes
            } for n_id, n in definition.nodes.items()
        }
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO workflow_definitions VALUES (?,?,?,?,?,?,?,?)",
                (
                    definition.id, definition.version, definition.name,
                    definition.state.value, json.dumps(nodes_dict), definition.start_node_id,
                    definition.created_at, definition.updated_at
                )
            )
            self._conn.commit()

    def get_definition(self, definition_id: str) -> Optional[WorkflowDefinition]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM workflow_definitions WHERE id = ?", (definition_id,)).fetchone()
            
        if not row:
            return None
            
        (id_, version, name, state, nodes_json, start_node_id, created_at, updated_at) = row
        nodes_raw = json.loads(nodes_json)
        nodes = {}
        for k, v in nodes_raw.items():
            nodes[k] = WorkflowNode(
                id=v["id"],
                type=StepType(v["type"]),
                name=v["name"],
                config=v["config"],
                next_nodes=v["next_nodes"]
            )
            
        return WorkflowDefinition(
            id=id_, version=version, name=name, state=WorkflowState(state),
            nodes=nodes, start_node_id=start_node_id, created_at=created_at, updated_at=updated_at
        )

    def save_run(self, run: WorkflowRun) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO workflow_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run.id, run.workflow_id, run.workflow_version, run.mission_id,
                    run.status.value, run.current_node_id, json.dumps(run.context),
                    run.correlation_id, run.created_at, run.updated_at,
                    run.started_at, run.finished_at, run.error,
                    run.attempt, run.max_attempts, run.locked_until
                )
            )
            self._conn.commit()

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
            
        if not row:
            return None
            
        return self._row_to_run(row)

    def _row_to_run(self, row) -> WorkflowRun:
        (id_, w_id, w_v, m_id, status, c_n_id, ctx, corr_id, c_at, u_at, s_at, f_at, err, att, m_att, l_until) = row
        return WorkflowRun(
            id=id_, workflow_id=w_id, workflow_version=w_v, mission_id=m_id,
            status=WorkflowRunStatus(status), current_node_id=c_n_id, context=json.loads(ctx),
            correlation_id=corr_id, created_at=c_at, updated_at=u_at, started_at=s_at,
            finished_at=f_at, error=err, attempt=att, max_attempts=m_att, locked_until=l_until
        )

    def list_runs_by_status(self, status: WorkflowRunStatus) -> List[WorkflowRun]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM workflow_runs WHERE status = ?", (status.value,)).fetchall()
        return [self._row_to_run(r) for r in rows]

    def save_step_run(self, step: WorkflowStepRun) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO workflow_step_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    step.id, step.run_id, step.node_id, step.status.value,
                    json.dumps(step.inputs), json.dumps(step.outputs), step.error,
                    step.started_at, step.finished_at, step.attempt
                )
            )
            self._conn.commit()

    def get_step_run(self, step_id: str) -> Optional[WorkflowStepRun]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM workflow_step_runs WHERE id = ?", (step_id,)).fetchone()
            if not row:
                return None
            (id_, run_id, node_id, status, inputs, outputs, err, s_at, f_at, att) = row
            return WorkflowStepRun(
                id=id_, run_id=run_id, node_id=node_id, status=WorkflowRunStatus(status),
                inputs=json.loads(inputs), outputs=json.loads(outputs), error=err,
                started_at=s_at, finished_at=f_at, attempt=att
            )

_default_store: Optional[WorkflowStore] = None

def get_default_store() -> WorkflowStore:
    global _default_store
    if _default_store is None:
        _default_store = WorkflowStore(Path(".data/workflows.db"))
    return _default_store
