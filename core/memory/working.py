"""
core.memory.working — working memory (Phase 5 spec, Parts 5-6).

Deliberately NOT persistent by default — it's an in-process, per-scope
dict-of-records with a bounded size, cleared when a task/session ends.
Promotion to episodic/semantic memory (see MemoryService.promote()) is the
explicit, controlled path for something in working memory to survive past
the current task.
"""
from __future__ import annotations

import logging
import threading
import time

from .models import MemoryRecord, MemoryType, Source

logger = logging.getLogger(__name__)

DEFAULT_MAX_ENTRIES_PER_SCOPE = 50
DEFAULT_MAX_CHARS_PER_SCOPE = 8000


class WorkingMemory:
    """Scoped by an arbitrary string key (typically a task_id or
    session_id) so multiple tasks' working memory never collide (spec Part
    18: namespace isolation) — each scope is independently size-bounded."""

    def __init__(self, max_entries_per_scope: int = DEFAULT_MAX_ENTRIES_PER_SCOPE,
                 max_chars_per_scope: int = DEFAULT_MAX_CHARS_PER_SCOPE):
        self._scopes: dict[str, dict[str, MemoryRecord]] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries_per_scope
        self._max_chars = max_chars_per_scope

    def set(self, scope: str, key: str, value: str, importance: float = 0.5,
            source: Source = Source.SYSTEM) -> MemoryRecord:
        record = MemoryRecord(
            content=value, memory_type=MemoryType.WORKING, memory_id=f"{scope}:{key}",
            namespace=f"session:{scope}", source=source, importance=importance,
            metadata={"scope": scope, "key": key},
        )
        with self._lock:
            bucket = self._scopes.setdefault(scope, {})
            bucket[key] = record
            self._enforce_limits_locked(scope)
        return record

    def get(self, scope: str, key: str) -> MemoryRecord | None:
        with self._lock:
            record = self._scopes.get(scope, {}).get(key)
            if record:
                record.touch_access()
            return record

    def update(self, scope: str, key: str, value: str) -> MemoryRecord | None:
        with self._lock:
            bucket = self._scopes.get(scope)
            if not bucket or key not in bucket:
                return None
        return self.set(scope, key, value)

    def remove(self, scope: str, key: str) -> bool:
        with self._lock:
            bucket = self._scopes.get(scope, {})
            existed = key in bucket
            bucket.pop(key, None)
            return existed

    def clear(self, scope: str) -> int:
        with self._lock:
            bucket = self._scopes.pop(scope, {})
            return len(bucket)

    def all(self, scope: str) -> list[MemoryRecord]:
        with self._lock:
            return list(self._scopes.get(scope, {}).values())

    def summarize(self, scope: str) -> str:
        """A plain-text join of current working memory for a scope — used
        as the (bounded, non-recursive) fallback when no model-based
        summarization is configured. See MemoryService.summarize_working()
        for the model-backed version."""
        records = self.all(scope)
        if not records:
            return ""
        lines = [f"- {r.metadata.get('key', r.memory_id)}: {r.content}" for r in records]
        return "\n".join(lines)

    def _enforce_limits_locked(self, scope: str) -> None:
        bucket = self._scopes.get(scope, {})
        while len(bucket) > self._max_entries:
            oldest_key = min(bucket, key=lambda k: bucket[k].created_at)
            del bucket[oldest_key]
            logger.debug("[WorkingMemory] scope=%s dropped oldest entry '%s' (entry limit)", scope, oldest_key)

        def _total_chars() -> int:
            return sum(len(r.content) for r in bucket.values())

        while bucket and _total_chars() > self._max_chars:
            oldest_key = min(bucket, key=lambda k: bucket[k].created_at)
            del bucket[oldest_key]
            logger.debug("[WorkingMemory] scope=%s dropped oldest entry '%s' (char limit)", scope, oldest_key)
