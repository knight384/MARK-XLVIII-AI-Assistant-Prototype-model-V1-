"""tests/agent/test_regression.py — Phase 4 spec Part 41 regression checks."""
from __future__ import annotations

from pathlib import Path

from core.agent.complexity import is_complex_request

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The exact 21 tool names from the Phase 3 baseline (be41151).
PHASE_3_TOOL_NAMES = {
    "open_app", "web_search", "system_status", "weather_report", "send_message",
    "reminder", "youtube_video", "screen_process", "close_camera", "computer_settings",
    "browser_control", "file_controller", "desktop_control", "code_helper", "dev_agent",
    "computer_control", "game_updater", "flight_finder", "shutdown_jarvis",
    "file_processor", "save_memory",
}


def test_all_21_phase_3_tools_remain_registered():
    from core.tools.registry import get_default_registry
    registry = get_default_registry()
    names = set(registry.list_names())
    missing = PHASE_3_TOOL_NAMES - names
    assert missing == set(), f"Phase 3 tools missing after Phase 4: {missing}"


def test_exactly_one_new_tool_added_when_agent_tools_registered():
    """Mirrors what main.py does at startup: register_agent_tools() adds
    exactly one new tool on top of the Phase 3 baseline set. Uses a FRESH
    ToolRegistry rather than the process-wide default singleton, so this
    test doesn't leak `run_agent_task` into tests/tools/'s assertions about
    the exact 21-tool Phase 3 baseline (those use the same shared
    singleton and run in the same pytest process)."""
    from core.agent.entrypoint import register_agent_tools
    from core.tools.definitions import register_all_tools
    from core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    register_all_tools(registry)
    register_agent_tools(registry)
    names = set(registry.list_names())
    added = names - PHASE_3_TOOL_NAMES
    assert added == {"run_agent_task"}, f"Unexpected tool set drift: {added}"


def test_main_py_still_uses_canonical_dispatcher_pattern():
    """Confirms Phase 4 did not reintroduce a second dispatch path or touch
    the realtime session loop."""
    main_py = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    assert "_tool_executor.execute(" in main_py
    assert "register_agent_tools" in main_py
    assert 'if name == "open_app"' not in main_py
    assert 'elif name ==' not in main_py
    # Realtime loop internals untouched — spot check key method names still present.
    for marker in ("_send_realtime", "_listen_audio", "_receive_audio", "_play_audio"):
        assert f"def {marker}" in main_py, f"expected {marker} still defined in main.py"


def test_gemini_live_adapter_still_used_not_replaced():
    main_py = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    assert "GeminiLiveAdapter" in main_py
    assert "genai.Client(" not in main_py


# -- complexity heuristic (informational utility, not wired to gate anything) -

def test_is_complex_request_detects_sequential_language():
    assert is_complex_request("Research the best database and then implement it.") is True


def test_is_complex_request_detects_multi_domain_verbs():
    assert is_complex_request("Analyze my project and fix the build error.") is True


def test_is_complex_request_false_for_simple_commands():
    assert is_complex_request("Open Chrome.") is False
    assert is_complex_request("What's the weather?") is False
    assert is_complex_request("Take a screenshot.") is False


def test_is_complex_request_handles_empty_string():
    assert is_complex_request("") is False
