"""
core.memory.episodic — episodic memory for meaningful events (Phase 5 spec,
Parts 12-13). Captures events, not raw conversation — callers decide what's
"meaningful" (task completed/failed, explicit user request to remember, a
significant tool/agent result); this module does not automatically persist
every interaction.
"""
from __future__ import annotations

from .models import MemoryRecord, MemoryType, Source
from .stores.base import MemoryStore


class EpisodicMemory:
    def __init__(self, store: MemoryStore):
        self._store = store

    def record_event(
        self,
        event: str,
        *,
        context: str = "",
        result: str = "",
        source: Source = Source.SYSTEM,
        related_task: str | None = None,
        related_project: str | None = None,
        importance: float = 0.5,
        namespace: str = "global",
        tags: tuple[str, ...] = (),
    ) -> MemoryRecord:
        content_parts = [event]
        if context:
            content_parts.append(f"Context: {context}")
        if result:
            content_parts.append(f"Result: {result}")
        content = "\n".join(content_parts)

        record = MemoryRecord(
            content=content, memory_type=MemoryType.EPISODIC, summary=event,
            source=source, importance=importance, namespace=namespace, tags=tags,
            project_id=related_project,
            metadata={"related_task": related_task, "related_project": related_project},
        )
        self._store.save(record)
        return record

    def recent(self, limit: int = 10, project_id: str | None = None) -> list[MemoryRecord]:
        records = self._store.search(memory_types=(MemoryType.EPISODIC,), project_id=project_id)
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    def for_task(self, task_id: str) -> list[MemoryRecord]:
        return [r for r in self._store.search(memory_types=(MemoryType.EPISODIC,))
                if r.metadata.get("related_task") == task_id]
