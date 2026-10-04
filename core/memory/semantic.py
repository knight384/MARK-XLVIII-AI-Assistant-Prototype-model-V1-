"""
core.memory.semantic — structured semantic memory: facts, concepts,
knowledge (Phase 5 spec, Part 14).

Semantic vector retrieval: NOT YET IMPLEMENTED. Retrieval here is
metadata/text-based only, via core.memory.retrieval.MemoryRetriever — the
same retriever used for episodic/project memory. This module only adds a
convenience `remember_fact()`/`facts_about()` API on top of that shared
retrieval path; it does not implement embeddings or a vector index (spec
Part 15: "Do not force vector search yet... clearly document: Semantic
vector retrieval is an extension point, not yet required.").
"""
from __future__ import annotations

from .models import MemoryRecord, MemoryType, Source
from .stores.base import MemoryStore


class SemanticMemory:
    def __init__(self, store: MemoryStore):
        self._store = store

    def remember_fact(
        self,
        fact: str,
        *,
        concept: str | None = None,
        source: Source = Source.SYSTEM,
        confidence: float = 0.7,
        tags: tuple[str, ...] = (),
        namespace: str = "global",
        project_id: str | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            content=fact, memory_type=MemoryType.SEMANTIC, summary=concept or "",
            source=source, confidence=confidence, tags=tags,
            namespace=namespace, project_id=project_id,
            metadata={"concept": concept} if concept else {},
        )
        self._store.save(record)
        return record

    def facts_about(self, concept: str, limit: int = 10) -> list[MemoryRecord]:
        records = [r for r in self._store.search(memory_types=(MemoryType.SEMANTIC,))
                   if r.metadata.get("concept") == concept]
        records.sort(key=lambda r: r.confidence, reverse=True)
        return records[:limit]

    def all_facts(self, namespace: str | None = None, project_id: str | None = None) -> list[MemoryRecord]:
        return self._store.search(memory_types=(MemoryType.SEMANTIC,), namespace=namespace,
                                   project_id=project_id)
