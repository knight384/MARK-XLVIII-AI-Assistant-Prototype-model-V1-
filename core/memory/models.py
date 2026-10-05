"""
core.memory.models — the storage-neutral MemoryRecord and MemoryType
(Phase 5 spec, Parts 3-4).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryType(str, Enum):
    WORKING = "working"
    PREFERENCE = "preference"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROJECT = "project"


class EntityType(str, Enum):
    """Types of entities in the structured knowledge graph."""
    PERSON = "person"
    PROJECT = "project"
    TOOL = "tool"
    PLACE = "place"
    CONCEPT = "concept"
    EVENT = "event"


class Source(str, Enum):
    """Provenance — 'do not treat every AI-generated statement as equally
    trustworthy' (spec Part 27)."""
    USER = "user"
    AGENT = "agent"
    TOOL = "tool"
    SYSTEM = "system"
    IMPORT = "import"


# Default confidence by source — explicit user statements are trusted more
# than inferred/agent-generated ones (spec Part 27), used when a caller
# doesn't supply an explicit confidence.
_DEFAULT_CONFIDENCE = {
    Source.USER: 1.0,
    Source.AGENT: 0.6,
    Source.TOOL: 0.7,
    Source.SYSTEM: 0.9,
    Source.IMPORT: 0.8,
}


@dataclass
class MemoryRecord:
    content: str
    memory_type: MemoryType
    memory_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    summary: str = ""
    source: Source = Source.SYSTEM
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_accessed_at: float | None = None
    importance: float = 0.5          # 0..1, caller-set or default; used in relevance scoring
    confidence: float = 0.8          # 0..1, provenance-derived trust
    tags: tuple[str, ...] = ()
    namespace: str = "global"        # e.g. "global" | "user" | "project:<id>" | "task:<id>" | "session:<id>"
    project_id: str | None = None
    user_id: str | None = None
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.confidence is None:
            self.confidence = _DEFAULT_CONFIDENCE.get(self.source, 0.5)

    def is_expired(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return self.expires_at is not None and now >= self.expires_at

    def touch_access(self) -> None:
        self.last_accessed_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["memory_type"] = self.memory_type.value
        d["source"] = self.source.value
        d["tags"] = list(self.tags)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MemoryRecord":
        d = dict(d)
        d["memory_type"] = MemoryType(d["memory_type"])
        d["source"] = Source(d.get("source", Source.SYSTEM.value))
        d["tags"] = tuple(d.get("tags", ()))
        return cls(**d)


@dataclass
class RetrievalQuery:
    """Provider/storage-neutral retrieval request (spec Part 20)."""
    query: str = ""
    memory_types: tuple[MemoryType, ...] = ()   # empty = all types
    namespace: str | None = None
    project_id: str | None = None
    tags: tuple[str, ...] = ()
    limit: int = 10
    min_relevance: float = 0.0


@dataclass
class RetrievalResult:
    record: MemoryRecord
    relevance: float
    reason: str = ""


# -- Phase 11 Structured Knowledge Models --

@dataclass
class KnowledgeEntity:
    name: str
    entity_type: EntityType
    entity_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    properties: dict[str, Any] = field(default_factory=dict)
    source: Source = Source.SYSTEM
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    namespace: str = "global"


@dataclass
class KnowledgeFact:
    subject_id: str
    predicate: str
    object_val: str
    fact_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    confidence: float = 1.0
    source: Source = Source.SYSTEM
    created_at: float = field(default_factory=time.time)
    namespace: str = "global"


@dataclass
class KnowledgeRelationship:
    from_id: str
    to_id: str
    rel_type: str
    rel_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    namespace: str = "global"
