"""
core.memory.policies — memory configuration (via Phase 1's ConfigService)
and retention/write policy helpers (Phase 5 spec, Parts 13, 23, 37-38).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryConfig:
    memory_enabled: bool = True
    working_memory_limit: int = 50          # max entries per working-memory scope
    working_memory_max_chars: int = 8000
    retrieval_limit: int = 10               # default RetrievalQuery.limit
    max_context_chars: int = 2000           # cap on memory text injected into any single prompt
    episodic_retention_days: int | None = 180   # None = no automatic expiry
    semantic_search_enabled: bool = True    # metadata/text search — NOT vector search (see retrieval.py)


def load_memory_config(config_service=None) -> MemoryConfig:
    """Reads memory.* settings from Phase 1's ConfigService, falling back
    to MemoryConfig's defaults. Does not introduce a second configuration
    system — every value is read through the existing `config.get(...)`
    (spec Part 37)."""
    if config_service is None:
        return MemoryConfig()

    return MemoryConfig(
        memory_enabled=bool(config_service.get("memory_enabled", True)),
        working_memory_limit=int(config_service.get("memory_working_limit", 50)),
        working_memory_max_chars=int(config_service.get("memory_working_max_chars", 8000)),
        retrieval_limit=int(config_service.get("memory_retrieval_limit", 10)),
        max_context_chars=int(config_service.get("memory_max_context_chars", 2000)),
        episodic_retention_days=config_service.get("memory_episodic_retention_days", 180),
        semantic_search_enabled=bool(config_service.get("memory_semantic_search_enabled", True)),
    )


# -- episodic write policy (spec Part 13) --------------------------------

_EPISODIC_TRIGGER_KEYWORDS = (
    "task completed", "task failed", "build fixed", "build failed",
    "user rejected", "user requested", "remember this", "milestone",
)


def should_record_episodic(event: str, *, explicit_request: bool = False,
                            task_completed: bool = False, task_failed: bool = False,
                            importance: float = 0.5) -> bool:
    """A simple, explicit rule set — NOT automatic for every event (spec
    Part 13: 'Do not automatically persist everything.'). Callers that know
    their event is meaningful (e.g. the Orchestrator on task completion)
    should generally just call EpisodicMemory.record_event() directly
    rather than routing through this predicate; it exists for callers that
    want a shared, explainable default policy instead of ad hoc judgment
    calls scattered around the codebase."""
    if explicit_request or task_completed or task_failed:
        return True
    if importance >= 0.8:
        return True
    lowered = event.lower()
    return any(kw in lowered for kw in _EPISODIC_TRIGGER_KEYWORDS)
