"""
tests/tools/test_regression.py — Phase 3 spec Part 34/35 regression checks.

Compares the tool name set that existed in main.py's hardcoded
TOOL_DECLARATIONS (as of the Phase 2 baseline commit e05bb03) against the
current Tool Registry. The expected difference is zero.
"""
from __future__ import annotations

from pathlib import Path

from core.tools.registry import get_default_registry

# Extracted directly from the Phase 2 baseline commit (e05bb03) main.py's
# TOOL_DECLARATIONS list — this is the pre-Phase-3 ground truth, not a
# re-derivation from the current registry (that would make the test
# tautological).
PRE_PHASE_3_TOOL_NAMES = {
    "open_app", "web_search", "system_status", "weather_report", "send_message",
    "reminder", "youtube_video", "screen_process", "close_camera", "computer_settings",
    "browser_control", "file_controller", "desktop_control", "code_helper", "dev_agent",
    "computer_control", "game_updater", "flight_finder", "shutdown_jarvis",
    "file_processor", "save_memory",
}


def test_no_tool_silently_disappeared():
    registry = get_default_registry()
    current_names = set(registry.list_names())
    missing = PRE_PHASE_3_TOOL_NAMES - current_names
    added = current_names - PRE_PHASE_3_TOOL_NAMES
    assert missing == set(), f"Tools present before Phase 3 but missing now: {missing}"
    assert added == set(), f"Undocumented new tools added in Phase 3: {added}"


def test_old_dispatcher_if_elif_chain_is_gone_from_main_py():
    """The old `if name == "...": ... elif name == "...":` chain must no
    longer be the active execution path (spec Part 35)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    main_py = (repo_root / "main.py").read_text(encoding="utf-8")
    # The old dispatcher had ~19 `elif name ==` branches. None should remain —
    # tool_name resolution now goes through registry.get()/executor.execute().
    assert 'elif name == "open_app"' not in main_py
    assert 'if name == "open_app"' not in main_py
    assert "_tool_executor.execute(" in main_py
    assert "_tool_registry" in main_py


def test_gemini_live_still_receives_function_declarations():
    """Confirms the Gemini schema adapter path (registry -> declarations)
    is actually wired into the Live session config in main.py."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    main_py = (repo_root / "main.py").read_text(encoding="utf-8")
    assert "TOOL_DECLARATIONS = _tool_registry.generate_gemini_declarations()" in main_py
    assert '"function_declarations": TOOL_DECLARATIONS' in main_py


def test_registry_generated_declarations_match_gemini_schema_shape():
    registry = get_default_registry()
    declarations = registry.generate_gemini_declarations()
    names = {d["name"] for d in declarations}
    assert names == PRE_PHASE_3_TOOL_NAMES
    for decl in declarations:
        assert decl["parameters"]["type"] == "OBJECT"
        assert "required" in decl["parameters"]
