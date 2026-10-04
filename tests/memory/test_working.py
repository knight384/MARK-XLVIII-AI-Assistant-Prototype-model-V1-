"""tests/memory/test_working.py"""
from __future__ import annotations

from core.memory.working import WorkingMemory


def test_set_and_get():
    wm = WorkingMemory()
    wm.set("task1", "plan", "do X then Y")
    record = wm.get("task1", "plan")
    assert record is not None
    assert record.content == "do X then Y"


def test_get_missing_returns_none():
    wm = WorkingMemory()
    assert wm.get("task1", "nonexistent") is None


def test_update():
    wm = WorkingMemory()
    wm.set("task1", "plan", "v1")
    wm.update("task1", "plan", "v2")
    assert wm.get("task1", "plan").content == "v2"


def test_update_missing_key_returns_none():
    wm = WorkingMemory()
    assert wm.update("task1", "nonexistent", "x") is None


def test_remove():
    wm = WorkingMemory()
    wm.set("task1", "plan", "x")
    assert wm.remove("task1", "plan") is True
    assert wm.get("task1", "plan") is None
    assert wm.remove("task1", "plan") is False


def test_clear():
    wm = WorkingMemory()
    wm.set("task1", "a", "1")
    wm.set("task1", "b", "2")
    removed = wm.clear("task1")
    assert removed == 2
    assert wm.all("task1") == []


def test_task_isolation():
    """Different scopes never see each other's entries (spec Part 18)."""
    wm = WorkingMemory()
    wm.set("task1", "key", "task1value")
    wm.set("task2", "key", "task2value")
    assert wm.get("task1", "key").content == "task1value"
    assert wm.get("task2", "key").content == "task2value"


def test_entry_limit_enforced():
    wm = WorkingMemory(max_entries_per_scope=3)
    for i in range(5):
        wm.set("task1", f"key{i}", f"value{i}")
    assert len(wm.all("task1")) == 3


def test_entry_limit_drops_oldest_first():
    wm = WorkingMemory(max_entries_per_scope=2)
    wm.set("task1", "first", "a")
    wm.set("task1", "second", "b")
    wm.set("task1", "third", "c")
    remaining_keys = {r.metadata["key"] for r in wm.all("task1")}
    assert "first" not in remaining_keys
    assert "third" in remaining_keys


def test_char_limit_enforced():
    wm = WorkingMemory(max_entries_per_scope=100, max_chars_per_scope=20)
    wm.set("task1", "a", "x" * 15)
    wm.set("task1", "b", "y" * 15)  # total now 30 > 20 -> should evict oldest
    total_chars = sum(len(r.content) for r in wm.all("task1"))
    assert total_chars <= 20


def test_summarize_plain_join():
    wm = WorkingMemory()
    wm.set("task1", "plan", "step 1")
    wm.set("task1", "status", "in progress")
    summary = wm.summarize("task1")
    assert "step 1" in summary
    assert "in progress" in summary


def test_summarize_empty_scope():
    wm = WorkingMemory()
    assert wm.summarize("nonexistent") == ""
