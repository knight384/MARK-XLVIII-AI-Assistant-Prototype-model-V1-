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

from ..models import (
    EntityType, KnowledgeEntity, KnowledgeFact, KnowledgeRelationship,
    MemoryRecord, MemoryType, Source
)
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

CREATE TABLE IF NOT EXISTS knowledge_entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    properties TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    namespace TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_k_ent_name ON knowledge_entities(name);
CREATE INDEX IF NOT EXISTS idx_k_ent_namespace ON knowledge_entities(namespace);

CREATE TABLE IF NOT EXISTS knowledge_facts (
    fact_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_val TEXT NOT NULL,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    created_at REAL NOT NULL,
    namespace TEXT NOT NULL,
    FOREIGN KEY(subject_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_k_fact_subj ON knowledge_facts(subject_id);

CREATE TABLE IF NOT EXISTS knowledge_relationships (
    rel_id TEXT PRIMARY KEY,
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    properties TEXT NOT NULL,
    created_at REAL NOT NULL,
    namespace TEXT NOT NULL,
    FOREIGN KEY(from_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY(to_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_k_rel_from ON knowledge_relationships(from_id);
CREATE INDEX IF NOT EXISTS idx_k_rel_to ON knowledge_relationships(to_id);
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

    # -- Structured Knowledge Graph API --

    def save_knowledge_entity(self, entity: KnowledgeEntity) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO knowledge_entities VALUES (?,?,?,?,?,?,?,?)",
                (entity.entity_id, entity.entity_type.value, entity.name, json.dumps(entity.properties),
                 entity.source.value, entity.created_at, entity.updated_at, entity.namespace)
            )
            self._conn.commit()

    def get_knowledge_entity(self, entity_id: str) -> KnowledgeEntity | None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM knowledge_entities WHERE entity_id = ?", (entity_id,))
            row = cur.fetchone()
        if not row:
            return None
        return KnowledgeEntity(
            entity_id=row[0], entity_type=EntityType(row[1]), name=row[2], properties=json.loads(row[3]),
            source=Source(row[4]), created_at=row[5], updated_at=row[6], namespace=row[7]
        )

    def search_knowledge_entities(self, name: str | None = None, entity_type: EntityType | None = None, namespace: str | None = None) -> list[KnowledgeEntity]:
        clauses, params = [], []
        if name:
            clauses.append("name = ?")
            params.append(name)
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type.value)
        if namespace:
            clauses.append("namespace = ?")
            params.append(namespace)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM knowledge_entities {where} ORDER BY updated_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        
        entities = []
        for r in rows:
            entities.append(KnowledgeEntity(
                entity_id=r[0], entity_type=EntityType(r[1]), name=r[2], properties=json.loads(r[3]),
                source=Source(r[4]), created_at=r[5], updated_at=r[6], namespace=r[7]
            ))
        return entities

    def search_knowledge_entities_by_term(self, term: str, namespace: str | None = None) -> list[KnowledgeEntity]:
        """Used for coarse retrieval matching entity name."""
        with self._lock:
            if namespace:
                rows = self._conn.execute(
                    "SELECT * FROM knowledge_entities WHERE name LIKE ? AND namespace = ?",
                    (f"%{term}%", namespace)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM knowledge_entities WHERE name LIKE ?",
                    (f"%{term}%",)
                ).fetchall()
        entities = []
        for r in rows:
            entities.append(KnowledgeEntity(
                entity_id=r[0], entity_type=EntityType(r[1]), name=r[2], properties=json.loads(r[3]),
                source=Source(r[4]), created_at=r[5], updated_at=r[6], namespace=r[7]
            ))
        return entities

    def save_knowledge_fact(self, fact: KnowledgeFact) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO knowledge_facts VALUES (?,?,?,?,?,?,?,?)",
                (fact.fact_id, fact.subject_id, fact.predicate, fact.object_val,
                 fact.confidence, fact.source.value, fact.created_at, fact.namespace)
            )
            self._conn.commit()

    def get_knowledge_facts_for_subject(self, subject_id: str) -> list[KnowledgeFact]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM knowledge_facts WHERE subject_id = ?", (subject_id,)).fetchall()
        
        facts = []
        for r in rows:
            facts.append(KnowledgeFact(
                fact_id=r[0], subject_id=r[1], predicate=r[2], object_val=r[3],
                confidence=r[4], source=Source(r[5]), created_at=r[6], namespace=r[7]
            ))
        return facts

    def search_knowledge_facts_by_term(self, term: str) -> list[KnowledgeFact]:
        """Used for coarse retrieval matching predicate or object_val."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM knowledge_facts WHERE predicate LIKE ? OR object_val LIKE ?",
                (f"%{term}%", f"%{term}%")
            ).fetchall()
        facts = []
        for r in rows:
            facts.append(KnowledgeFact(
                fact_id=r[0], subject_id=r[1], predicate=r[2], object_val=r[3],
                confidence=r[4], source=Source(r[5]), created_at=r[6], namespace=r[7]
            ))
        return facts

    def save_knowledge_relationship(self, rel: KnowledgeRelationship) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO knowledge_relationships VALUES (?,?,?,?,?,?,?)",
                (rel.rel_id, rel.from_id, rel.to_id, rel.rel_type, json.dumps(rel.properties),
                 rel.created_at, rel.namespace)
            )
            self._conn.commit()

    def get_knowledge_relationships_for_entity(self, entity_id: str) -> list[KnowledgeRelationship]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM knowledge_relationships WHERE from_id = ? OR to_id = ?",
                (entity_id, entity_id)
            ).fetchall()
        
        rels = []
        for r in rows:
            rels.append(KnowledgeRelationship(
                rel_id=r[0], from_id=r[1], to_id=r[2], rel_type=r[3], properties=json.loads(r[4]),
                created_at=r[5], namespace=r[6]
            ))
        return rels

    def close(self) -> None:
        with self._lock:
            self._conn.close()
