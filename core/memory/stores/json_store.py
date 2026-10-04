"""
core.memory.stores.json_store — JSON-file-backed MemoryStore (Phase 5 spec,
Part 10). Used for preference memory (small, infrequently-written, and this
matches the existing memory/long_term.json's storage model, which Phase 5
migrates rather than replaces outright).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from ..models import MemoryRecord, MemoryType
from .base import MemoryStore

logger = logging.getLogger(__name__)


class JsonMemoryStore(MemoryStore):
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._data = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._data = raw if isinstance(raw, dict) else {}
        except Exception as exc:
            logger.error("Failed to load JSON memory store at %s (%s) — starting empty.",
                         self._path, type(exc).__name__)
            self._data = {}

    def _flush_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def save(self, record: MemoryRecord) -> None:
        with self._lock:
            self._data[record.memory_id] = record.to_dict()
            self._flush_locked()

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            raw = self._data.get(memory_id)
            return MemoryRecord.from_dict(raw) if raw else None

    def update(self, record: MemoryRecord) -> None:
        record.updated_at = time.time()
        self.save(record)

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            existed = memory_id in self._data
            self._data.pop(memory_id, None)
            if existed:
                self._flush_locked()
            return existed

    def delete_by_namespace(self, namespace: str) -> int:
        with self._lock:
            to_remove = [mid for mid, raw in self._data.items() if raw.get("namespace") == namespace]
            for mid in to_remove:
                del self._data[mid]
            if to_remove:
                self._flush_locked()
            return len(to_remove)

    def delete_by_project(self, project_id: str) -> int:
        with self._lock:
            to_remove = [mid for mid, raw in self._data.items() if raw.get("project_id") == project_id]
            for mid in to_remove:
                del self._data[mid]
            if to_remove:
                self._flush_locked()
            return len(to_remove)

    def search(self, memory_types=(), namespace=None, project_id=None, tags=(), limit=None) -> list[MemoryRecord]:
        with self._lock:
            records = [MemoryRecord.from_dict(raw) for raw in self._data.values()]
        return _filter_records(records, memory_types, namespace, project_id, tags, limit)

    def all(self) -> list[MemoryRecord]:
        with self._lock:
            return [MemoryRecord.from_dict(raw) for raw in self._data.values()]

    def purge_expired(self, now: float | None = None) -> int:
        now = now if now is not None else time.time()
        with self._lock:
            to_remove = [mid for mid, raw in self._data.items()
                         if raw.get("expires_at") is not None and now >= raw["expires_at"]]
            for mid in to_remove:
                del self._data[mid]
            if to_remove:
                self._flush_locked()
            return len(to_remove)


def _filter_records(records: list[MemoryRecord], memory_types, namespace, project_id, tags,
                     limit) -> list[MemoryRecord]:
    if memory_types:
        records = [r for r in records if r.memory_type in memory_types]
    if namespace is not None:
        records = [r for r in records if r.namespace == namespace]
    if project_id is not None:
        records = [r for r in records if r.project_id == project_id]
    if tags:
        records = [r for r in records if set(tags) & set(r.tags)]
    if limit is not None:
        records = records[:limit]
    return records
