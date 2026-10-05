"""
core.memory.service — the central MemoryService (Phase 5 spec, Part 9).

This is the ONLY thing agents/runtime code should talk to for memory.
Nothing outside core/memory/ should import a MemoryStore, open
memory/long_term.json, or otherwise touch storage directly (spec Part 1,
enforced by tests/memory/test_architecture.py's static check).
"""
from __future__ import annotations

import logging
import re
import threading
import time

from .episodic import EpisodicMemory
from .errors import MemoryError
from .migration import MigrationReport, migrate_legacy_json
from .models import MemoryRecord, MemoryType, RetrievalQuery, RetrievalResult, Source
from .policies import MemoryConfig, load_memory_config
from .preferences import PreferenceMemory
from .projects import ProjectMemory, derive_project_id
from .retrieval import MemoryRetriever
from .semantic import SemanticMemory
from .knowledge import KnowledgeMemory
from .stores.base import MemoryStore
from .stores.json_store import JsonMemoryStore
from .stores.sqlite_store import SqliteMemoryStore
from .working import WorkingMemory

logger = logging.getLogger(__name__)

# Lightweight secret-shaped guard (spec Part 36) — mirrors
# core/logging_setup.py's redaction patterns for consistency, but here the
# goal is refusing to STORE the value at all, not just redacting a log line.
_SECRET_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"bearer\s+[A-Za-z0-9\-._~+/]{20,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),   # Gemini API key shape
]


def _looks_like_secret(text: str) -> bool:
    return any(p.search(text) for p in _SECRET_PATTERNS)


class MemoryService:
    def __init__(
        self,
        preference_store: MemoryStore,
        durable_store: MemoryStore,   # episodic + semantic + project
        config: MemoryConfig | None = None,
        legacy_json_path=None,
    ):
        self._config = config or MemoryConfig()
        self._preferences = PreferenceMemory(preference_store)
        self._episodic = EpisodicMemory(durable_store)
        self._semantic = SemanticMemory(durable_store)
        self._projects = ProjectMemory(durable_store)
        self._working = WorkingMemory(
            max_entries_per_scope=self._config.working_memory_limit,
            max_chars_per_scope=self._config.working_memory_max_chars,
        )
        self._knowledge = KnowledgeMemory(durable_store)
        self._retriever = MemoryRetriever([preference_store, durable_store], knowledge=self._knowledge)
        self._lock = threading.Lock()

        self.migration_report: MigrationReport | None = None
        if legacy_json_path is not None:
            self.migration_report = migrate_legacy_json(legacy_json_path, self._preferences)
            if self.migration_report.ran and not self.migration_report.error:
                logger.info("[Memory] %s", self.migration_report.summary())

    # -- typed sub-layer access (for callers that want a specific layer) ---

    @property
    def working(self) -> WorkingMemory:
        return self._working

    @property
    def preferences(self) -> PreferenceMemory:
        return self._preferences

    @property
    def episodic(self) -> EpisodicMemory:
        return self._episodic

    @property
    def semantic(self) -> SemanticMemory:
        return self._semantic

    @property
    def projects(self) -> ProjectMemory:
        return self._projects

    @property
    def knowledge(self) -> KnowledgeMemory:
        return self._knowledge

    @property
    def config(self) -> MemoryConfig:
        return self._config

    # -- generic service API (spec Part 9) ----------------------------

    def remember(self, content: str, memory_type: MemoryType, *, namespace: str = "global",
                 source: Source = Source.SYSTEM, importance: float = 0.5,
                 project_id: str | None = None, tags: tuple[str, ...] = (),
                 expires_at: float | None = None) -> MemoryRecord | None:
        """Generic write path. Returns None (and logs a warning, does not
        raise) if memory is disabled or the content looks like a secret —
        see _looks_like_secret() and spec Part 36."""
        if not self._config.memory_enabled:
            logger.debug("[Memory] remember() skipped — memory_enabled=False")
            return None
        if _looks_like_secret(content):
            logger.warning("[Memory] Refused to store a value that looks like a secret "
                            "(type=%s, namespace=%s).", memory_type.value, namespace)
            return None

        record = MemoryRecord(
            content=content, memory_type=memory_type, namespace=namespace, source=source,
            importance=importance, project_id=project_id, tags=tags, expires_at=expires_at,
        )
        store = self._store_for(memory_type)
        store.save(record)
        logger.info("[Memory] stored type=%s namespace=%s", memory_type.value, namespace)
        return record

    def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        if not self._config.memory_enabled:
            return []
        try:
            query = RetrievalQuery(
                query=query.query, memory_types=query.memory_types, namespace=query.namespace,
                project_id=query.project_id, tags=query.tags,
                limit=min(query.limit, self._config.retrieval_limit) if query.limit else self._config.retrieval_limit,
                min_relevance=query.min_relevance,
            )
            results = self._retriever.retrieve(query)
            logger.info("[Memory] retrieved %d result(s) for query type(s)=%s", len(results), query.memory_types)
            return results
        except Exception as exc:
            # A memory retrieval failure must not crash an unrelated task
            # (spec Part 40) — log and return empty, the caller proceeds
            # without optional memory context.
            logger.warning("[Memory] retrieve() failed (%s) — continuing without memory.", exc)
            return []

    def get(self, memory_id: str, memory_type: MemoryType) -> MemoryRecord | None:
        return self._store_for(memory_type).get(memory_id)

    def update(self, record: MemoryRecord) -> None:
        self._store_for(record.memory_type).update(record)

    def forget(self, memory_id: str, memory_type: MemoryType) -> bool:
        return self._store_for(memory_type).delete(memory_id)

    def forget_by_namespace(self, namespace: str) -> int:
        return sum(store.delete_by_namespace(namespace) for store in self._all_stores())

    def forget_by_project(self, project_id: str) -> int:
        return sum(store.delete_by_project(project_id) for store in self._all_stores())

    def clear_working(self, scope: str) -> int:
        return self._working.clear(scope)

    def summarize(self, scope: str, model_gateway=None) -> str:
        """Plain-text summary of working memory for a scope. Uses the
        Model Gateway ONLY if provided and the working-memory content
        exceeds a size threshold (spec Part 24: 'Do not call the model for
        every memory operation.') — otherwise returns the deterministic
        join from WorkingMemory.summarize()."""
        plain = self._working.summarize(scope)
        if not plain or model_gateway is None or len(plain) < 1500:
            return plain
        try:
            from core.llm.types import Message, ModelRequest
            request = ModelRequest(messages=[Message(
                role="user",
                content=f"Summarize this working context concisely, preserving key facts:\n\n{plain}",
            )])
            response = model_gateway.generate(request, task_type="fast")
            return response.content.strip() or plain
        except Exception as exc:
            logger.warning("[Memory] summarize() model call failed (%s) — returning plain join.", exc)
            return plain

    # -- promotion (spec Part 25) ---------------------------------------

    def promote_to_episodic(self, scope: str, key: str, event: str, *, importance: float = 0.6,
                             related_task: str | None = None) -> MemoryRecord | None:
        """Working memory -> episodic memory, explicit only (no autonomous
        promotion — spec Part 25: 'Use explicit rules initially.')."""
        working_record = self._working.get(scope, key)
        if working_record is None:
            return None
        return self._episodic.record_event(
            event, context=working_record.content, source=Source.AGENT,
            related_task=related_task, importance=importance,
        )

    def promote_to_semantic(self, episodic_record: MemoryRecord, concept: str,
                             confidence: float = 0.7) -> MemoryRecord:
        """Episodic event -> a stable semantic fact, explicit only."""
        return self._semantic.remember_fact(
            episodic_record.summary or episodic_record.content, concept=concept,
            source=Source.AGENT, confidence=confidence,
        )

    def demote(self, memory_id: str, memory_type: MemoryType, *, new_importance: float = 0.2) -> None:
        record = self.get(memory_id, memory_type)
        if record is not None:
            record.importance = new_importance
            self.update(record)

    # -- convenience -------------------------------------------------------

    def project_id_for(self, repo_path, explicit_id: str | None = None) -> str:
        return derive_project_id(repo_path, explicit_id)

    def preference_context_text(self) -> str:
        """The text injected into the Gemini Live system prompt — same
        contract as the legacy format_memory_for_prompt()."""
        return self._preferences.format_for_prompt()

    def purge_expired(self) -> int:
        return sum(store.purge_expired() for store in self._all_stores())

    def _store_for(self, memory_type: MemoryType) -> MemoryStore:
        if memory_type == MemoryType.PREFERENCE:
            return self._preferences._store  # noqa: SLF001 — internal, same module family
        return self._episodic._store  # noqa: SLF001 — episodic/semantic/project share one durable store

    def _all_stores(self) -> list[MemoryStore]:
        return [self._preferences._store, self._episodic._store]  # noqa: SLF001


_default_service: MemoryService | None = None
_default_lock = threading.Lock()


def get_default_memory_service() -> MemoryService:
    global _default_service
    with _default_lock:
        if _default_service is not None:
            return _default_service

        from core.config import get_config_service
        config_service = get_config_service()
        memory_config = load_memory_config(config_service)
        paths = config_service.paths()

        preference_store = JsonMemoryStore(paths.memory_dir / "preferences.json")
        durable_store = SqliteMemoryStore(paths.memory_dir / "memory.db")
        legacy_path = paths.memory_dir / "long_term.json"

        _default_service = MemoryService(
            preference_store=preference_store, durable_store=durable_store,
            config=memory_config, legacy_json_path=legacy_path,
        )
        return _default_service
