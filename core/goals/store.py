import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional, List

from .models import Goal, GoalState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    owner TEXT NOT NULL,
    state TEXT NOT NULL,
    priority INTEGER NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    target_time REAL,
    progress REAL NOT NULL,
    parent_id TEXT,
    milestones TEXT NOT NULL,
    related_projects TEXT NOT NULL,
    related_missions TEXT NOT NULL,
    metadata TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_goal_state ON goals(state);
"""

class GoalStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save(self, goal: Goal) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO goals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    goal.id, goal.title, goal.description, goal.owner, goal.state.value,
                    goal.priority, goal.created_at, goal.updated_at, goal.target_time,
                    goal.progress, goal.parent_id,
                    json.dumps([m.to_dict() for m in goal.milestones]),
                    json.dumps(goal.related_projects),
                    json.dumps(goal.related_missions),
                    json.dumps(goal.metadata)
                )
            )
            self._conn.commit()

    def get(self, goal_id: str) -> Optional[Goal]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        return self._row_to_goal(row) if row else None

    def list_goals(self, state: Optional[GoalState] = None) -> List[Goal]:
        sql = "SELECT * FROM goals"
        params = []
        if state:
            sql += " WHERE state = ?"
            params.append(state.value)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_goal(r) for r in rows]

    def _row_to_goal(self, row: tuple) -> Goal:
        return Goal.from_dict({
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "owner": row[3],
            "state": row[4],
            "priority": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "target_time": row[8],
            "progress": row[9],
            "parent_id": row[10],
            "milestones": json.loads(row[11]),
            "related_projects": json.loads(row[12]),
            "related_missions": json.loads(row[13]),
            "metadata": json.loads(row[14])
        })

_default_store: Optional[GoalStore] = None

def get_default_goal_store() -> GoalStore:
    global _default_store
    if _default_store is None:
        _default_store = GoalStore(Path(".data/goals.db"))
    return _default_store
