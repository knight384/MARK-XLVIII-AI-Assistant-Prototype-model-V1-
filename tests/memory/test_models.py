"""tests/memory/test_models.py"""
from __future__ import annotations

import time

from core.memory.models import MemoryRecord, MemoryType, Source


def test_record_creation_defaults():
    record = MemoryRecord(content="hello", memory_type=MemoryType.SEMANTIC)
    assert record.memory_id
    assert record.namespace == "global"
    assert record.source == Source.SYSTEM
    assert 0 <= record.confidence <= 1


def test_record_confidence_defaults_by_source():
    user_record = MemoryRecord(content="x", memory_type=MemoryType.PREFERENCE, source=Source.USER, confidence=None)
    agent_record = MemoryRecord(content="x", memory_type=MemoryType.SEMANTIC, source=Source.AGENT, confidence=None)
    assert user_record.confidence > agent_record.confidence  # user statements trusted more (spec Part 27)


def test_record_to_dict_and_from_dict_roundtrip():
    record = MemoryRecord(content="hello", memory_type=MemoryType.EPISODIC, tags=("a", "b"),
                           namespace="project:x", project_id="x")
    d = record.to_dict()
    restored = MemoryRecord.from_dict(d)
    assert restored.content == record.content
    assert restored.memory_type == record.memory_type
    assert restored.tags == record.tags
    assert restored.namespace == record.namespace


def test_record_is_expired():
    now = time.time()
    expired = MemoryRecord(content="x", memory_type=MemoryType.WORKING, expires_at=now - 10)
    not_expired = MemoryRecord(content="x", memory_type=MemoryType.WORKING, expires_at=now + 1000)
    never_expires = MemoryRecord(content="x", memory_type=MemoryType.WORKING)
    assert expired.is_expired(now) is True
    assert not_expired.is_expired(now) is False
    assert never_expires.is_expired(now) is False


def test_record_touch_access_sets_timestamp():
    record = MemoryRecord(content="x", memory_type=MemoryType.SEMANTIC)
    assert record.last_accessed_at is None
    record.touch_access()
    assert record.last_accessed_at is not None


def test_namespace_isolation_field_present():
    a = MemoryRecord(content="x", memory_type=MemoryType.PROJECT, namespace="project:a", project_id="a")
    b = MemoryRecord(content="y", memory_type=MemoryType.PROJECT, namespace="project:b", project_id="b")
    assert a.namespace != b.namespace
    assert a.project_id != b.project_id
