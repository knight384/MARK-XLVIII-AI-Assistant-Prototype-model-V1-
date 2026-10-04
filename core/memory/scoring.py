"""
core.memory.scoring — deterministic, explainable relevance scoring (Phase 5
spec, Parts 21-22). No LLM call is used to rank memories — a future
embedding-based retriever can augment/replace this, but is explicitly out
of scope for Phase 5 (see core/memory/retrieval.py's module docstring).
"""
from __future__ import annotations

import re
import time

from .models import MemoryRecord, RetrievalQuery

# Weights are intentionally simple/explainable (spec Part 22: "keep the
# scoring explainable. Don't overfit the formula.").
_WEIGHT_TEXT_MATCH = 0.4
_WEIGHT_NAMESPACE_MATCH = 0.15
_WEIGHT_PROJECT_MATCH = 0.15
_WEIGHT_RECENCY = 0.1
_WEIGHT_IMPORTANCE = 0.1
_WEIGHT_CONFIDENCE = 0.1

_RECENCY_HALF_LIFE_SECONDS = 14 * 24 * 3600  # 14 days — recent memories score higher, decaying smoothly


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _text_match_score(query: str, record: MemoryRecord) -> float:
    if not query:
        return 0.0
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    content_tokens = _tokenize(record.content) | _tokenize(record.summary) | set(record.tags)
    if not content_tokens:
        return 0.0
    overlap = query_tokens & content_tokens
    return len(overlap) / len(query_tokens)


def _recency_score(record: MemoryRecord, now: float) -> float:
    age = max(0.0, now - record.updated_at)
    return 0.5 ** (age / _RECENCY_HALF_LIFE_SECONDS)


def score_record(query: RetrievalQuery, record: MemoryRecord, now: float | None = None) -> tuple[float, str]:
    """Returns (relevance, human-readable reason) — the reason exists so
    debug logging can explain a ranking without dumping memory content
    (spec Part 35: 'Show which memories were selected in debug logs when
    appropriate, but never log private memory contents')."""
    now = now if now is not None else time.time()

    text = _text_match_score(query.query, record)
    namespace = 1.0 if (query.namespace and record.namespace == query.namespace) else 0.0
    project = 1.0 if (query.project_id and record.project_id == query.project_id) else 0.0
    recency = _recency_score(record, now)
    importance = max(0.0, min(1.0, record.importance))
    confidence = max(0.0, min(1.0, record.confidence))

    relevance = (
        _WEIGHT_TEXT_MATCH * text
        + _WEIGHT_NAMESPACE_MATCH * namespace
        + _WEIGHT_PROJECT_MATCH * project
        + _WEIGHT_RECENCY * recency
        + _WEIGHT_IMPORTANCE * importance
        + _WEIGHT_CONFIDENCE * confidence
    )

    reason = (
        f"text={text:.2f} namespace={namespace:.0f} project={project:.0f} "
        f"recency={recency:.2f} importance={importance:.2f} confidence={confidence:.2f}"
    )
    return relevance, reason
