"""core.memory.stores.base — the MemoryStore interface (Phase 5 spec, Part 10)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import MemoryRecord, MemoryType


class MemoryStore(ABC):
    """Storage-neutral interface. Never exposed directly to agents — only
    MemoryService talks to a MemoryStore (spec Part 1: 'Memory is a
    service, not a file')."""

    @abstractmethod
    def save(self, record: MemoryRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, memory_id: str) -> MemoryRecord | None:
        raise NotImplementedError

    @abstractmethod
    def update(self, record: MemoryRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_by_namespace(self, namespace: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def delete_by_project(self, project_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def search(self, memory_types: tuple[MemoryType, ...] = (), namespace: str | None = None,
               project_id: str | None = None, tags: tuple[str, ...] = (),
               limit: int | None = None) -> list[MemoryRecord]:
        """Coarse pre-filtering only (type/namespace/project/tags) — text
        relevance scoring happens in core.memory.scoring, not here, so
        every MemoryStore implementation stays simple."""
        raise NotImplementedError

    @abstractmethod
    def all(self) -> list[MemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    def purge_expired(self, now: float | None = None) -> int:
        raise NotImplementedError
