"""
core.memory.retrieval — bounded, scored memory retrieval (Phase 5 spec,
Part 20).

Semantic vector retrieval: NOT YET IMPLEMENTED (spec Part 15/46). This
module does coarse store-level filtering (type/namespace/project/tags) via
each MemoryStore's `search()`, then deterministic text/metadata relevance
scoring (core/memory/scoring.py) — not embedding similarity. The
`MemoryRetriever` interface below is the extension point a future
`VectorSemanticStore` could plug into without changing callers.
"""
from __future__ import annotations

import logging
import time

from .models import MemoryRecord, RetrievalQuery, RetrievalResult
from .scoring import score_record
from .stores.base import MemoryStore
from .knowledge import KnowledgeMemory

logger = logging.getLogger(__name__)

_MAX_RETRIEVAL_LIMIT = 50   # hard ceiling regardless of what a caller requests (spec Part 23)


class MemoryRetriever:
    """Wraps one or more MemoryStores and applies bounded, scored
    retrieval. A future vector-based retriever can implement the same
    `retrieve()` signature."""

    def __init__(self, stores: list[MemoryStore], knowledge: KnowledgeMemory | None = None):
        self._stores = stores
        self._knowledge = knowledge

    def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        limit = max(1, min(query.limit, _MAX_RETRIEVAL_LIMIT))
        now = time.time()

        candidates: list[MemoryRecord] = []
        for store in self._stores:
            candidates.extend(store.search(
                memory_types=query.memory_types, namespace=query.namespace,
                project_id=query.project_id, tags=query.tags,
            ))
            
        if self._knowledge:
            # Synthesize Knowledge Graph profiles and add to candidates
            candidates.extend(self._knowledge.retrieve_profiles_as_records(query.query, query.namespace))

        candidates = [c for c in candidates if not c.is_expired(now)]

        scored: list[RetrievalResult] = []
        for record in candidates:
            relevance, reason = score_record(query, record, now=now)
            if relevance >= query.min_relevance:
                scored.append(RetrievalResult(record=record, relevance=relevance, reason=reason))

        scored.sort(key=lambda r: r.relevance, reverse=True)
        results = scored[:limit]

        for r in results:
            r.record.touch_access()

        logger.debug("[Memory] retrieval: query=%r types=%s namespace=%s project=%s -> %d result(s)",
                     query.query[:40], query.memory_types, query.namespace, query.project_id, len(results))
        return results
