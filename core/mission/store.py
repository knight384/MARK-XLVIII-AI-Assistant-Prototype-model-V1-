from __future__ import annotations
import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from .models import Mission, MissionState

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    owner TEXT NOT NULL,
    state TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    scheduled_at REAL,
    timezone TEXT NOT NULL,
    cron_expression TEXT,
    trigger_event TEXT,
    condition_metadata TEXT NOT NULL,
    priority INTEGER NOT NULL,
    current_task_id TEXT,
    last_execution_at REAL,
    next_execution_at REAL,
    max_attempts INTEGER NOT NULL,
    attempt_count INTEGER NOT NULL,
    retry_metadata TEXT NOT NULL,
    result_summary TEXT,
    error_state TEXT,
    metadata TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mission_state ON missions(state);
CREATE INDEX IF NOT EXISTS idx_mission_trigger ON missions(trigger_type);
"""

class MissionStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _row_to_mission(self, row: tuple) -> Mission:
        (mid, name, description, owner, state, trigger_type, created_at, updated_at,
         scheduled_at, timezone, cron_expression, trigger_event, condition_metadata,
         priority, current_task_id, last_execution_at, next_execution_at,
         max_attempts, attempt_count, retry_metadata, result_summary, error_state,
         metadata) = row
         
        return Mission.from_dict({
            "id": mid,
            "name": name,
            "description": description,
            "owner": owner,
            "state": state,
            "trigger_type": trigger_type,
            "created_at": created_at,
            "updated_at": updated_at,
            "scheduled_at": scheduled_at,
            "timezone": timezone,
            "cron_expression": cron_expression,
            "trigger_event": trigger_event,
            "condition_metadata": json.loads(condition_metadata),
            "priority": priority,
            "current_task_id": current_task_id,
            "last_execution_at": last_execution_at,
            "next_execution_at": next_execution_at,
            "max_attempts": max_attempts,
            "attempt_count": attempt_count,
            "retry_metadata": json.loads(retry_metadata),
            "result_summary": result_summary,
            "error_state": error_state,
            "metadata": json.loads(metadata),
        })

    def save(self, mission: Mission) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO missions VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    mission.id, mission.name, mission.description, mission.owner,
                    mission.state.value, mission.trigger_type.value, mission.created_at,
                    mission.updated_at, mission.scheduled_at, mission.timezone,
                    mission.cron_expression, mission.trigger_event,
                    json.dumps(mission.condition_metadata), mission.priority,
                    mission.current_task_id, mission.last_execution_at,
                    mission.next_execution_at, mission.max_attempts, mission.attempt_count,
                    json.dumps(mission.retry_metadata), mission.result_summary,
                    mission.error_state, json.dumps(mission.metadata)
                )
            )
            self._conn.commit()

    def get(self, mission_id: str) -> Optional[Mission]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM missions WHERE id = ?", (mission_id,))
            row = cur.fetchone()
        return self._row_to_mission(row) if row else None

    def delete(self, mission_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM missions WHERE id = ?", (mission_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def list_missions(self, state: Optional[MissionState] = None) -> list[Mission]:
        sql = "SELECT * FROM missions"
        params = []
        if state:
            sql += " WHERE state = ?"
            params.append(state.value)
        sql += " ORDER BY created_at DESC"
        
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_mission(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

_default_store: Optional[MissionStore] = None

def get_default_store() -> MissionStore:
    global _default_store
    if _default_store is None:
        _default_store = MissionStore(Path(".data/missions.db"))
    return _default_store
