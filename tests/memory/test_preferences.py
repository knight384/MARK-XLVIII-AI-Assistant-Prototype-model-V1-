"""tests/memory/test_preferences.py"""
from __future__ import annotations

from core.memory.models import Source
from core.memory.preferences import MAX_VALUE_LENGTH, MEMORY_MAX_CHARS, PreferenceMemory, VALID_CATEGORIES


def test_valid_categories_match_legacy():
    assert VALID_CATEGORIES == ("identity", "preferences", "projects", "relationships", "wishes", "notes")


def test_set_and_get(preference_store):
    pm = PreferenceMemory(preference_store)
    pm.set("identity", "name", "Vikram")
    assert pm.get("identity", "name") == "Vikram"


def test_invalid_category_falls_back_to_notes(preference_store):
    pm = PreferenceMemory(preference_store)
    pm.set("nonexistent_category", "key", "value")
    assert pm.get("notes", "key") == "value"


def test_forget(preference_store):
    pm = PreferenceMemory(preference_store)
    pm.set("identity", "name", "Vikram")
    assert pm.forget("identity", "name") is True
    assert pm.get("identity", "name") is None
    assert pm.forget("identity", "name") is False


def test_value_truncation(preference_store):
    pm = PreferenceMemory(preference_store)
    long_value = "x" * (MAX_VALUE_LENGTH + 100)
    pm.set("notes", "long", long_value)
    stored = pm.get("notes", "long")
    assert len(stored) <= MAX_VALUE_LENGTH + 1  # +1 for ellipsis char


def test_as_categorized_dict_shape(preference_store):
    pm = PreferenceMemory(preference_store)
    pm.set("identity", "name", "Vikram")
    pm.set("preferences", "food", "pizza")
    d = pm.as_categorized_dict()
    assert set(VALID_CATEGORIES).issubset(d.keys())
    assert d["identity"]["name"]["value"] == "Vikram"
    assert "updated" in d["identity"]["name"]


def test_format_for_prompt_includes_identity_and_preferences(preference_store):
    pm = PreferenceMemory(preference_store)
    pm.set("identity", "name", "Vikram")
    pm.set("preferences", "food", "pizza")
    text = pm.format_for_prompt()
    assert "Vikram" in text
    assert "pizza" in text
    assert "WHAT YOU KNOW ABOUT THIS PERSON" in text


def test_format_for_prompt_empty_returns_empty_string(preference_store):
    pm = PreferenceMemory(preference_store)
    assert pm.format_for_prompt() == ""


def test_format_for_prompt_bounded_length(preference_store):
    pm = PreferenceMemory(preference_store)
    for i in range(50):
        pm.set("notes", f"note{i}", "x" * 100)
    text = pm.format_for_prompt()
    assert len(text) <= 2001  # matches the legacy 2000-char cap + ellipsis


def test_identity_fields_helper(preference_store):
    pm = PreferenceMemory(preference_store)
    pm.set("identity", "name", "Vikram")
    pm.set("identity", "city", "Mumbai")
    fields = pm.identity_fields()
    assert fields == {"name": "Vikram", "city": "Mumbai"}


def test_total_size_limit_trims_oldest(preference_store):
    pm = PreferenceMemory(preference_store)
    for i in range(20):
        pm.set("notes", f"note{i}", "x" * 200)
    total = sum(len(v) for v in [pm.get("notes", f"note{i}") or "" for i in range(20)])
    assert total <= MEMORY_MAX_CHARS
    assert pm.get("notes", "note0") is None  # earliest notes evicted first


def test_source_provenance_recorded(preference_store):
    pm = PreferenceMemory(preference_store)
    pm.set("identity", "name", "Vikram", source=Source.USER)
    record = preference_store.get("pref:identity:name")
    assert record.source == Source.USER
