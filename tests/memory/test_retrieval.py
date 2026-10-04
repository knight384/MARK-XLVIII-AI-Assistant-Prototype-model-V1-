"""tests/memory/test_retrieval.py"""
from __future__ import annotations

import time

from core.memory.models import MemoryRecord, MemoryType, RetrievalQuery
from core.memory.retrieval import MemoryRetriever
from core.memory.scoring import score_record


def test_query_text_matching(durable_store):
    durable_store.save(MemoryRecord(content="the user loves dark mode themes", memory_type=MemoryType.SEMANTIC))
    durable_store.save(MemoryRecord(content="completely unrelated content", memory_type=MemoryType.SEMANTIC))
    retriever = MemoryRetriever([durable_store])
    results = retriever.retrieve(RetrievalQuery(query="dark mode"))
    assert results[0].record.content.startswith("the user loves")


def test_type_filtering(durable_store):
    durable_store.save(MemoryRecord(content="a", memory_type=MemoryType.SEMANTIC))
    durable_store.save(MemoryRecord(content="b", memory_type=MemoryType.EPISODIC))
    retriever = MemoryRetriever([durable_store])
    results = retriever.retrieve(RetrievalQuery(memory_types=(MemoryType.EPISODIC,)))
    assert len(results) == 1
    assert results[0].record.memory_type == MemoryType.EPISODIC


def test_namespace_filtering(durable_store):
    durable_store.save(MemoryRecord(content="a", memory_type=MemoryType.SEMANTIC, namespace="ns1"))
    durable_store.save(MemoryRecord(content="b", memory_type=MemoryType.SEMANTIC, namespace="ns2"))
    retriever = MemoryRetriever([durable_store])
    results = retriever.retrieve(RetrievalQuery(namespace="ns1"))
    assert len(results) == 1


def test_project_filtering(durable_store):
    durable_store.save(MemoryRecord(content="a", memory_type=MemoryType.PROJECT, project_id="p1"))
    durable_store.save(MemoryRecord(content="b", memory_type=MemoryType.PROJECT, project_id="p2"))
    retriever = MemoryRetriever([durable_store])
    results = retriever.retrieve(RetrievalQuery(project_id="p1"))
    assert len(results) == 1


def test_retrieval_is_bounded_by_limit(durable_store):
    for i in range(20):
        durable_store.save(MemoryRecord(content=f"item {i}", memory_type=MemoryType.SEMANTIC))
    retriever = MemoryRetriever([durable_store])
    results = retriever.retrieve(RetrievalQuery(limit=5))
    assert len(results) == 5


def test_retrieval_hard_ceiling_regardless_of_requested_limit(durable_store):
    for i in range(80):
        durable_store.save(MemoryRecord(content=f"item {i}", memory_type=MemoryType.SEMANTIC))
    retriever = MemoryRetriever([durable_store])
    results = retriever.retrieve(RetrievalQuery(limit=1000))  # way over the hard ceiling
    assert len(results) <= 50


def test_expired_records_excluded(durable_store):
    durable_store.save(MemoryRecord(content="expired", memory_type=MemoryType.WORKING,
                                     expires_at=time.time() - 10))
    durable_store.save(MemoryRecord(content="fresh", memory_type=MemoryType.WORKING,
                                     expires_at=time.time() + 1000))
    retriever = MemoryRetriever([durable_store])
    results = retriever.retrieve(RetrievalQuery())
    contents = [r.record.content for r in results]
    assert "expired" not in contents
    assert "fresh" in contents


def test_min_relevance_filters_low_scores(durable_store):
    durable_store.save(MemoryRecord(content="completely irrelevant text", memory_type=MemoryType.SEMANTIC,
                                     importance=0.0, confidence=0.0))
    retriever = MemoryRetriever([durable_store])
    results = retriever.retrieve(RetrievalQuery(query="something totally different", min_relevance=0.9))
    assert results == []


def test_results_sorted_by_relevance_descending(durable_store):
    durable_store.save(MemoryRecord(content="python programming language", memory_type=MemoryType.SEMANTIC,
                                     importance=0.9))
    durable_store.save(MemoryRecord(content="unrelated cooking recipe", memory_type=MemoryType.SEMANTIC,
                                     importance=0.1))
    retriever = MemoryRetriever([durable_store])
    results = retriever.retrieve(RetrievalQuery(query="python programming"))
    assert results[0].relevance >= results[-1].relevance


def test_retrieval_touches_access_timestamp(durable_store):
    record = MemoryRecord(content="something", memory_type=MemoryType.SEMANTIC)
    durable_store.save(record)
    retriever = MemoryRetriever([durable_store])
    results = retriever.retrieve(RetrievalQuery(query="something"))
    assert results[0].record.last_accessed_at is not None


# -- scoring internals ----------------------------------------------------

def test_score_record_returns_explainable_reason():
    record = MemoryRecord(content="test content", memory_type=MemoryType.SEMANTIC)
    relevance, reason = score_record(RetrievalQuery(query="test"), record)
    assert 0 <= relevance <= 1
    assert "text=" in reason and "recency=" in reason and "importance=" in reason


def test_score_higher_importance_scores_higher_all_else_equal():
    low = MemoryRecord(content="x", memory_type=MemoryType.SEMANTIC, importance=0.1, confidence=0.5)
    high = MemoryRecord(content="x", memory_type=MemoryType.SEMANTIC, importance=0.9, confidence=0.5)
    now = time.time()
    low_score, _ = score_record(RetrievalQuery(), low, now=now)
    high_score, _ = score_record(RetrievalQuery(), high, now=now)
    assert high_score > low_score


def test_score_recency_decays_over_time():
    now = time.time()
    old = MemoryRecord(content="x", memory_type=MemoryType.SEMANTIC)
    old.updated_at = now - (60 * 24 * 3600)  # 60 days old
    fresh = MemoryRecord(content="x", memory_type=MemoryType.SEMANTIC)
    fresh.updated_at = now
    old_score, _ = score_record(RetrievalQuery(), old, now=now)
    fresh_score, _ = score_record(RetrievalQuery(), fresh, now=now)
    assert fresh_score > old_score
