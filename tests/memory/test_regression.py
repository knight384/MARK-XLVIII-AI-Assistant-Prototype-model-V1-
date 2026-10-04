"""tests/memory/test_regression.py — Phase 5 spec Part 43 regression checks."""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PHASE_3_TOOL_NAMES = {
    "open_app", "web_search", "system_status", "weather_report", "send_message",
    "reminder", "youtube_video", "screen_process", "close_camera", "computer_settings",
    "browser_control", "file_controller", "desktop_control", "code_helper", "dev_agent",
    "computer_control", "game_updater", "flight_finder", "shutdown_jarvis",
    "file_processor", "save_memory",
}


def test_all_21_original_tools_remain_registered():
    from core.tools.registry import get_default_registry
    names = set(get_default_registry().list_names())
    missing = PHASE_3_TOOL_NAMES - names
    assert missing == set()


def test_run_agent_task_remains_available():
    """register_agent_tools() (called by main.py at startup) still adds the
    Phase 4 entry point tool cleanly on top of the Phase 3 baseline. Uses
    an isolated registry rather than the shared default singleton, to
    avoid depending on whether an earlier test already registered it on the
    shared registry (Phase 4's tests deliberately avoid mutating the shared
    singleton — see tests/agent/test_regression.py)."""
    from core.agent.entrypoint import register_agent_tools
    from core.tools.definitions import register_all_tools
    from core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    register_all_tools(registry)
    register_agent_tools(registry)
    assert registry.exists("run_agent_task")


def test_main_py_unmodified_by_phase_5():
    """Phase 5 deliberately made zero changes to main.py — the legacy
    memory_manager compatibility shim means main.py's existing
    load_memory()/format_memory_for_prompt() calls keep working unchanged."""
    main_py = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    assert "from memory.memory_manager import" in main_py
    assert "load_memory" in main_py
    assert "format_memory_for_prompt" in main_py
    # Still routes tools through the Phase 3/4 registry/executor, unaffected.
    assert "_tool_executor.execute(" in main_py
    assert "GeminiLiveAdapter" in main_py


def test_agent_registry_still_works():
    from core.agent.registry import get_default_agent_registry
    registry = get_default_agent_registry()
    expected = {"developer_agent", "research_agent", "browser_agent",
                "computer_agent", "file_document_agent", "verification_agent"}
    assert set(registry.list_ids()) == expected


def test_legacy_long_term_json_shape_remains_migratable(tmp_path):
    """A realistic legacy file (matching the actual pre-Phase-5 shape) must
    still migrate cleanly."""
    from core.memory.migration import migrate_legacy_json
    from core.memory.preferences import PreferenceMemory
    from core.memory.stores.json_store import JsonMemoryStore

    legacy = tmp_path / "long_term.json"
    legacy.write_text(json.dumps({
        "identity": {"name": {"value": "Vikram", "updated": "2025-06-01"}},
        "preferences": {},
        "projects": {"jarvis": {"value": "AI assistant project", "updated": "2025-06-01"}},
        "relationships": {},
        "wishes": {},
        "notes": {},
    }), encoding="utf-8")

    pm = PreferenceMemory(JsonMemoryStore(tmp_path / "prefs.json"))
    report = migrate_legacy_json(legacy, pm)

    assert report.error is None
    assert pm.get("identity", "name") == "Vikram"
    assert pm.get("projects", "jarvis") == "AI assistant project"


def test_memory_manager_shim_backward_compatible_api(tmp_path, monkeypatch):
    """The legacy public API (load_memory, update_memory,
    format_memory_for_prompt, remember, forget) still works exactly as
    before, just backed by the new service. Uses an isolated, tmp_path-backed
    MemoryService (monkeypatched in) rather than the real default service,
    so this test never touches the actual repo's memory/ directory."""
    from core.memory.policies import MemoryConfig
    from core.memory.service import MemoryService
    from core.memory.stores.json_store import JsonMemoryStore
    from core.memory.stores.sqlite_store import SqliteMemoryStore

    isolated_service = MemoryService(
        JsonMemoryStore(tmp_path / "prefs.json"),
        SqliteMemoryStore(tmp_path / "mem.db"),
        config=MemoryConfig(),
    )
    monkeypatch.setattr("core.memory.get_default_memory_service", lambda: isolated_service)

    import memory.memory_manager as mm

    result = mm.remember("test_key", "test_value", category="notes")
    assert "test_key" in result
    memory = mm.load_memory()
    assert memory["notes"]["test_key"]["value"] == "test_value"

    text = mm.format_memory_for_prompt(memory)
    assert isinstance(text, str)

    forget_result = mm.forget("test_key", category="notes")
    assert "Forgotten" in forget_result
