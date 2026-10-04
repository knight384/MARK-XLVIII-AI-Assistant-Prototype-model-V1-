"""tests/memory/test_service.py"""
from __future__ import annotations

from core.memory.models import MemoryType, RetrievalQuery, Source
from core.memory.policies import MemoryConfig
from core.memory.service import MemoryService


def test_remember_and_retrieve(memory_service):
    memory_service.remember("User likes dark mode", MemoryType.SEMANTIC, source=Source.USER)
    results = memory_service.retrieve(RetrievalQuery(query="dark mode"))
    assert len(results) == 1


def test_remember_preference_uses_preference_store(memory_service, preference_store):
    memory_service.remember("x", MemoryType.PREFERENCE)
    assert len(preference_store.all()) == 1


def test_remember_episodic_uses_durable_store(memory_service, durable_store):
    memory_service.remember("event happened", MemoryType.EPISODIC)
    assert len(durable_store.all()) == 1


def test_get_update_forget(memory_service):
    record = memory_service.remember("x", MemoryType.SEMANTIC)
    fetched = memory_service.get(record.memory_id, MemoryType.SEMANTIC)
    assert fetched.content == "x"

    fetched.content = "y"
    memory_service.update(fetched)
    assert memory_service.get(record.memory_id, MemoryType.SEMANTIC).content == "y"

    assert memory_service.forget(record.memory_id, MemoryType.SEMANTIC) is True
    assert memory_service.get(record.memory_id, MemoryType.SEMANTIC) is None


def test_forget_by_namespace(memory_service):
    memory_service.remember("a", MemoryType.SEMANTIC, namespace="ns1")
    memory_service.remember("b", MemoryType.SEMANTIC, namespace="ns2")
    removed = memory_service.forget_by_namespace("ns1")
    assert removed == 1


def test_forget_by_project(memory_service):
    memory_service.remember("a", MemoryType.PROJECT, project_id="p1")
    memory_service.remember("b", MemoryType.PROJECT, project_id="p2")
    removed = memory_service.forget_by_project("p1")
    assert removed == 1


def test_clear_working(memory_service):
    memory_service.working.set("task1", "a", "1")
    memory_service.working.set("task1", "b", "2")
    removed = memory_service.clear_working("task1")
    assert removed == 2


def test_summarize_returns_plain_join_for_short_content(memory_service):
    memory_service.working.set("task1", "plan", "step 1")
    summary = memory_service.summarize("task1")
    assert "step 1" in summary


def test_summarize_empty_scope_returns_empty_string(memory_service):
    assert memory_service.summarize("nonexistent") == ""


def test_promote_to_episodic(memory_service):
    memory_service.working.set("task1", "decision", "chose SQLite over Postgres")
    record = memory_service.promote_to_episodic("task1", "decision", "Made a storage decision")
    assert record is not None
    assert "chose SQLite" in record.content


def test_promote_to_episodic_missing_working_key_returns_none(memory_service):
    assert memory_service.promote_to_episodic("task1", "nonexistent", "event") is None


def test_promote_to_semantic(memory_service):
    episodic = memory_service.episodic.record_event("Repeated fact observed")
    semantic = memory_service.promote_to_semantic(episodic, concept="observation")
    assert semantic.memory_type == MemoryType.SEMANTIC


def test_demote_lowers_importance(memory_service):
    record = memory_service.remember("x", MemoryType.SEMANTIC, importance=0.9)
    memory_service.demote(record.memory_id, MemoryType.SEMANTIC, new_importance=0.1)
    updated = memory_service.get(record.memory_id, MemoryType.SEMANTIC)
    assert updated.importance == 0.1


def test_project_id_for(memory_service, tmp_path):
    pid = memory_service.project_id_for(tmp_path, explicit_id="explicit-id")
    assert pid == "explicit-id"


def test_preference_context_text(memory_service):
    memory_service.preferences.set("identity", "name", "Vikram")
    text = memory_service.preference_context_text()
    assert "Vikram" in text


def test_purge_expired(memory_service):
    import time
    memory_service.remember("expired", MemoryType.SEMANTIC, expires_at=time.time() - 10)
    memory_service.remember("fresh", MemoryType.SEMANTIC, expires_at=time.time() + 1000)
    purged = memory_service.purge_expired()
    assert purged == 1


# -- disabled mode (spec Part 38) ----------------------------------------

def test_disabled_mode_skips_writes(memory_service_disabled, durable_store):
    result = memory_service_disabled.remember("should not persist", MemoryType.SEMANTIC)
    assert result is None
    assert durable_store.all() == []


def test_disabled_mode_returns_empty_retrieval(memory_service_disabled):
    results = memory_service_disabled.retrieve(RetrievalQuery(query="anything"))
    assert results == []


def test_disabled_mode_working_memory_still_usable_for_execution(memory_service_disabled):
    """Spec Part 38: 'working memory may remain in-memory for the current
    operation if necessary for execution' even when persistent memory is
    disabled — WorkingMemory itself is never persistent regardless."""
    memory_service_disabled.working.set("task1", "plan", "do X")
    assert memory_service_disabled.working.get("task1", "plan").content == "do X"


# -- privacy (spec Part 36, tested per Part 42) ---------------------------

def test_refuses_to_store_api_key_shaped_value(memory_service, durable_store):
    result = memory_service.remember("my api_key is AIzaSyFAKE1234567890FAKE", MemoryType.SEMANTIC)
    assert result is None
    assert durable_store.all() == []


def test_refuses_to_store_password_shaped_value(memory_service, durable_store):
    result = memory_service.remember("my password is hunter2", MemoryType.SEMANTIC)
    assert result is None


def test_refuses_to_store_bearer_token_shaped_value(memory_service, durable_store):
    result = memory_service.remember(
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789ABCD", MemoryType.SEMANTIC,
    )
    assert result is None


def test_normal_content_is_not_blocked(memory_service):
    result = memory_service.remember("User's favorite color is blue", MemoryType.SEMANTIC)
    assert result is not None


def test_memory_can_be_deleted(tmp_path):
    """Spec Part 50 acceptance: 'Memory can be deleted.'"""
    from core.memory.stores.json_store import JsonMemoryStore
    from core.memory.stores.sqlite_store import SqliteMemoryStore
    service = MemoryService(JsonMemoryStore(tmp_path / "p.json"), SqliteMemoryStore(tmp_path / "d.db"))
    record = service.remember("deletable", MemoryType.SEMANTIC)
    assert service.forget(record.memory_id, MemoryType.SEMANTIC) is True
