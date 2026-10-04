"""
tests/memory/test_stores.py — parametrized against both MemoryStore
implementations, since they must satisfy the same interface.
"""
from __future__ import annotations

import pytest

from core.memory.models import MemoryRecord, MemoryType
from core.memory.stores.json_store import JsonMemoryStore
from core.memory.stores.sqlite_store import SqliteMemoryStore


@pytest.fixture(params=["json", "sqlite"])
def store(request, tmp_path):
    if request.param == "json":
        return JsonMemoryStore(tmp_path / "store.json")
    return SqliteMemoryStore(tmp_path / "store.db")


def test_save_and_get(store):
    record = MemoryRecord(content="hello", memory_type=MemoryType.SEMANTIC)
    store.save(record)
    fetched = store.get(record.memory_id)
    assert fetched is not None
    assert fetched.content == "hello"


def test_get_missing_returns_none(store):
    assert store.get("nonexistent") is None


def test_update(store):
    record = MemoryRecord(content="v1", memory_type=MemoryType.SEMANTIC)
    store.save(record)
    record.content = "v2"
    store.update(record)
    assert store.get(record.memory_id).content == "v2"


def test_delete(store):
    record = MemoryRecord(content="x", memory_type=MemoryType.SEMANTIC)
    store.save(record)
    assert store.delete(record.memory_id) is True
    assert store.get(record.memory_id) is None
    assert store.delete(record.memory_id) is False  # already gone


def test_delete_by_namespace(store):
    store.save(MemoryRecord(content="a", memory_type=MemoryType.SEMANTIC, namespace="ns1"))
    store.save(MemoryRecord(content="b", memory_type=MemoryType.SEMANTIC, namespace="ns1"))
    store.save(MemoryRecord(content="c", memory_type=MemoryType.SEMANTIC, namespace="ns2"))
    removed = store.delete_by_namespace("ns1")
    assert removed == 2
    assert len(store.search(namespace="ns2")) == 1


def test_delete_by_project(store):
    store.save(MemoryRecord(content="a", memory_type=MemoryType.PROJECT, project_id="p1"))
    store.save(MemoryRecord(content="b", memory_type=MemoryType.PROJECT, project_id="p2"))
    removed = store.delete_by_project("p1")
    assert removed == 1
    assert len(store.search(project_id="p2")) == 1


def test_search_by_type(store):
    store.save(MemoryRecord(content="a", memory_type=MemoryType.SEMANTIC))
    store.save(MemoryRecord(content="b", memory_type=MemoryType.EPISODIC))
    results = store.search(memory_types=(MemoryType.SEMANTIC,))
    assert len(results) == 1
    assert results[0].content == "a"


def test_search_by_tags(store):
    store.save(MemoryRecord(content="a", memory_type=MemoryType.SEMANTIC, tags=("python", "coding")))
    store.save(MemoryRecord(content="b", memory_type=MemoryType.SEMANTIC, tags=("cooking",)))
    results = store.search(tags=("python",))
    assert len(results) == 1
    assert results[0].content == "a"


def test_search_limit(store):
    for i in range(5):
        store.save(MemoryRecord(content=f"item{i}", memory_type=MemoryType.SEMANTIC))
    results = store.search(limit=2)
    assert len(results) == 2


def test_all(store):
    store.save(MemoryRecord(content="a", memory_type=MemoryType.SEMANTIC))
    store.save(MemoryRecord(content="b", memory_type=MemoryType.EPISODIC))
    assert len(store.all()) == 2


def test_purge_expired(store):
    import time
    store.save(MemoryRecord(content="expired", memory_type=MemoryType.WORKING, expires_at=time.time() - 10))
    store.save(MemoryRecord(content="fresh", memory_type=MemoryType.WORKING, expires_at=time.time() + 1000))
    purged = store.purge_expired()
    assert purged == 1
    assert len(store.all()) == 1
    assert store.all()[0].content == "fresh"


def test_json_store_persists_across_instances(tmp_path):
    path = tmp_path / "persist.json"
    store1 = JsonMemoryStore(path)
    record = MemoryRecord(content="persisted", memory_type=MemoryType.PREFERENCE)
    store1.save(record)

    store2 = JsonMemoryStore(path)  # fresh instance, same file
    fetched = store2.get(record.memory_id)
    assert fetched is not None
    assert fetched.content == "persisted"


def test_sqlite_store_persists_across_instances(tmp_path):
    path = tmp_path / "persist.db"
    store1 = SqliteMemoryStore(path)
    record = MemoryRecord(content="persisted", memory_type=MemoryType.EPISODIC)
    store1.save(record)
    store1.close()

    store2 = SqliteMemoryStore(path)
    fetched = store2.get(record.memory_id)
    assert fetched is not None
    assert fetched.content == "persisted"
