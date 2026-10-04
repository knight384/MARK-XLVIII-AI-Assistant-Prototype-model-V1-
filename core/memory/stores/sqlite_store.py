"""
core.memory.stores.sqlite_store — SQLite-backed MemoryStore (Phase 5 spec,
Part 11).

Decision/rationale (documented per spec Part 11's requirement): episodic,
semantic, and project memory can grow to many more records than the small,
hand-curated preference set, and benefit from indexed lookups by namespace/
project/type and safe concurrent writes across multiple agents in one
orchestrated task (spec Part 39). JSON's whole-file-rewrite-per-write model
(as used for PreferenceMemory, matching the existing memory/long_term.json
behavior) doesn't scale well to that pattern. SQLite meets the "genuinely
needs concurrent access, indexed queries, reliable updates, multiple
namespaces" bar from Part 11 without introducing a server process or new
infrastructure — it's stdlib (`sqlite3`), a single file, and safe for this
single-process application via a lock around write operations (Part 39:
"Do not overengineer distributed concurrency" — a thread lock is enough for
one process).

Working memory does NOT use this store — it's deliberately non-persistent
(see core/memory/working.py).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path

from ..models import MemoryRecord, MemoryType
from .base import MemoryStore

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_records (
    memory_id TEXT PRIMARY KEY,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_accessed_at REAL,
    importance REAL NOT NULL,
    confidence REAL NOT NULL,
    tags TEXT NOT NULL,
    namespace TEXT NOT NULL,
    project_id TEXT,
    user_id TEXT,
    expires_at REAL,
    metadata TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_records(memory_type);
CREATE INDEX IF NOT EXISTS idx_namespace ON memory_records(namespace);
CREATE INDEX IF NOT EXISTS idx_project_id ON memory_records(project_id);
"""


class SqliteMemoryStore(MemoryStore):
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _row_to_record(self, row: tuple) -> MemoryRecord:
        (memory_id, memory_type, content, summary, source, created_at, updated_at,
         last_accessed_at, importance, confidence, tags_json, namespace, project_id,
         user_id, expires_at, metadata_json) = row
        return MemoryRecord.from_dict({
            "memory_id": memory_id, "memory_type": memory_type, "content": content,
            "summary": summary or "", "source": source, "created_at": created_at,
            "updated_at": updated_at, "last_accessed_at": last_accessed_at,
            "importance": importance, "confidence": confidence,
            "tags": json.loads(tags_json), "namespace": namespace, "project_id": project_id,
            "user_id": user_id, "expires_at": expires_at, "metadata": json.loads(metadata_json),
        })

    def save(self, record: MemoryRecord) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO memory_records VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.memory_id, record.memory_type.value, record.content, record.summary,
                    record.source.value, record.created_at, record.updated_at,
                    record.last_accessed_at, record.importance, record.confidence,
                    json.dumps(list(record.tags)), record.namespace, record.project_id,
                    record.user_id, record.expires_at, json.dumps(record.metadata),
                ),
            )
            self._conn.commit()

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM memory_records WHERE memory_id = ?", (memory_id,))
            row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def update(self, record: MemoryRecord) -> None:
        record.updated_at = time.time()
        self.save(record)

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM memory_records WHERE memory_id = ?", (memory_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def delete_by_namespace(self, namespace: str) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM memory_records WHERE namespace = ?", (namespace,))
            self._conn.commit()
            return cur.rowcount

    def delete_by_project(self, project_id: str) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM memory_records WHERE project_id = ?", (project_id,))
            self._conn.commit()
            return cur.rowcount

    def search(self, memory_types=(), namespace=None, project_id=None, tags=(), limit=None) -> list[MemoryRecord]:
        clauses, params = [], []
        if memory_types:
            placeholders = ",".join("?" * len(memory_types))
            clauses.append(f"memory_type IN ({placeholders})")
            params.extend(t.value for t in memory_types)
        if namespace is not None:
            clauses.append("namespace = ?")
            params.append(namespace)
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM memory_records {where} ORDER BY updated_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        records = [self._row_to_record(r) for r in rows]
        if tags:
            records = [r for r in records if set(tags) & set(r.tags)]
        if limit is not None:
            records = records[:limit]
        return records

    def all(self) -> list[MemoryRecord]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM memory_records").fetchall()
        return [self._row_to_record(r) for r in rows]

    def purge_expired(self, now: float | None = None) -> int:
        now = now if now is not None else time.time()
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memory_records WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
