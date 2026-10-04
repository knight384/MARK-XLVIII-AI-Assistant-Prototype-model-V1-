"""tests/memory/test_migration.py"""
from __future__ import annotations

import json

from core.memory.migration import migrate_legacy_json
from core.memory.preferences import PreferenceMemory


def _write_legacy(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_migration_of_nonexistent_file_is_a_noop(tmp_path, preference_store):
    pm = PreferenceMemory(preference_store)
    report = migrate_legacy_json(tmp_path / "nonexistent.json", pm)
    assert report.ran is False


def test_migration_imports_all_categories(tmp_path, preference_store):
    legacy = tmp_path / "long_term.json"
    _write_legacy(legacy, {
        "identity": {"name": {"value": "Vikram"}},
        "preferences": {"food": {"value": "pizza"}},
        "projects": {"jarvis": {"value": "AI assistant"}},
        "relationships": {"sister": {"value": "Priya"}},
        "wishes": {"goal": {"value": "learn Rust"}},
        "notes": {"misc": {"value": "likes coffee"}},
    })
    pm = PreferenceMemory(preference_store)
    report = migrate_legacy_json(legacy, pm)

    assert report.ran is True
    assert report.error is None
    assert report.imported_count == 6
    assert pm.get("identity", "name") == "Vikram"
    assert pm.get("relationships", "sister") == "Priya"
    assert pm.get("wishes", "goal") == "learn Rust"


def test_migration_no_data_loss(tmp_path, preference_store):
    legacy = tmp_path / "long_term.json"
    _write_legacy(legacy, {"notes": {f"note{i}": {"value": f"value{i}"} for i in range(10)}})
    pm = PreferenceMemory(preference_store)
    migrate_legacy_json(legacy, pm)
    for i in range(10):
        assert pm.get("notes", f"note{i}") == f"value{i}"


def test_migration_is_idempotent(tmp_path, preference_store):
    legacy = tmp_path / "long_term.json"
    _write_legacy(legacy, {"identity": {"name": {"value": "Vikram"}}})
    pm = PreferenceMemory(preference_store)

    report1 = migrate_legacy_json(legacy, pm)
    report2 = migrate_legacy_json(legacy, pm)

    assert report1.imported_count == 1
    assert report2.imported_count == 0  # second run: nothing new to import
    assert report2.skipped_existing_count == 1


def test_migration_does_not_overwrite_user_changed_value(tmp_path, preference_store):
    """If the user has since changed a value through the new system, a
    re-run of migration must not clobber it with the stale legacy value."""
    legacy = tmp_path / "long_term.json"
    _write_legacy(legacy, {"identity": {"name": {"value": "OldName"}}})
    pm = PreferenceMemory(preference_store)
    migrate_legacy_json(legacy, pm)

    pm.set("identity", "name", "NewName")  # user updates it via the new system
    migrate_legacy_json(legacy, pm)  # re-run migration

    assert pm.get("identity", "name") == "NewName"  # not clobbered back to OldName


def test_migration_never_deletes_legacy_file(tmp_path, preference_store):
    legacy = tmp_path / "long_term.json"
    _write_legacy(legacy, {"identity": {"name": {"value": "Vikram"}}})
    pm = PreferenceMemory(preference_store)
    migrate_legacy_json(legacy, pm)
    assert legacy.exists()


def test_migration_reports_parse_failure_without_raising(tmp_path, preference_store):
    legacy = tmp_path / "long_term.json"
    legacy.write_text("not valid json{{{", encoding="utf-8")
    pm = PreferenceMemory(preference_store)
    report = migrate_legacy_json(legacy, pm)  # must not raise
    assert report.ran is True
    assert report.error is not None


def test_migration_skips_unknown_categories(tmp_path, preference_store):
    legacy = tmp_path / "long_term.json"
    _write_legacy(legacy, {"unknown_category": {"key": {"value": "x"}}})
    pm = PreferenceMemory(preference_store)
    report = migrate_legacy_json(legacy, pm)
    assert report.imported_count == 0


def test_migration_via_memory_service_constructor(tmp_path, preference_store, durable_store):
    """The MemoryService itself triggers migration when given a
    legacy_json_path, matching how get_default_memory_service() wires it."""
    legacy = tmp_path / "long_term.json"
    _write_legacy(legacy, {"identity": {"name": {"value": "Vikram"}}})

    from core.memory.service import MemoryService
    service = MemoryService(preference_store, durable_store, legacy_json_path=legacy)

    assert service.migration_report.ran is True
    assert service.preferences.get("identity", "name") == "Vikram"
