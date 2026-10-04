"""tests/memory/test_episodic.py"""
from __future__ import annotations

from core.memory.episodic import EpisodicMemory
from core.memory.policies import should_record_episodic


def test_record_event(durable_store):
    em = EpisodicMemory(durable_store)
    record = em.record_event("Task completed", result="build succeeded", importance=0.8)
    assert record.summary == "Task completed"
    assert "build succeeded" in record.content


def test_recent_ordered_by_creation(durable_store):
    em = EpisodicMemory(durable_store)
    em.record_event("first event")
    em.record_event("second event")
    recent = em.recent(limit=10)
    assert recent[0].summary == "second event"  # most recent first


def test_recent_respects_limit(durable_store):
    em = EpisodicMemory(durable_store)
    for i in range(5):
        em.record_event(f"event {i}")
    assert len(em.recent(limit=2)) == 2


def test_for_task(durable_store):
    em = EpisodicMemory(durable_store)
    em.record_event("event A", related_task="task-1")
    em.record_event("event B", related_task="task-2")
    results = em.for_task("task-1")
    assert len(results) == 1
    assert results[0].summary == "event A"


def test_recent_filtered_by_project(durable_store):
    em = EpisodicMemory(durable_store)
    em.record_event("proj a event", related_project="proj-a")
    em.record_event("proj b event", related_project="proj-b")
    results = em.recent(project_id="proj-a")
    assert len(results) == 1


# -- write policy (spec Part 13) -----------------------------------------

def test_should_record_on_explicit_request():
    assert should_record_episodic("anything", explicit_request=True) is True


def test_should_record_on_task_completed():
    assert should_record_episodic("anything", task_completed=True) is True


def test_should_record_on_task_failed():
    assert should_record_episodic("anything", task_failed=True) is True


def test_should_record_on_high_importance():
    assert should_record_episodic("routine thing", importance=0.9) is True


def test_should_not_record_routine_low_importance_event():
    assert should_record_episodic("clicked a button", importance=0.3) is False


def test_should_record_on_trigger_keyword():
    assert should_record_episodic("The build failed due to a syntax error") is True
