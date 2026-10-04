"""tests/llm/test_regression.py — Phase 2 regression checks (spec Part 31 'Regression tests')."""
from __future__ import annotations

import re
from pathlib import Path

from .conftest import FakeProvider, make_model
from core.llm.router import ModelRouter


def test_gemini_available_routes_to_gemini_by_default(empty_registry):
    gemini = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash", tool_calling=True)])
    empty_registry.register("gemini", lambda: gemini)
    router = ModelRouter(empty_registry)
    decision = router.route("default")
    assert decision.provider_id == "gemini"


def test_dispatcher_and_tool_declarations_unchanged():
    """Phase 2 checked that main.py's 19-branch tool dispatcher was untouched.

    Phase 3 deliberately REMOVED that dispatcher (that was Phase 3's whole
    point) and replaced TOOL_DECLARATIONS with registry-generated schemas —
    see core/tools/. This test is updated accordingly: it now verifies tool
    availability via the Tool Registry (the new source of truth) instead of
    grepping for literal tool-name strings in main.py, which no longer
    contains them by design.
    """
    from core.tools import get_default_registry
    registry = get_default_registry()
    names = set(registry.list_names())
    for tool_name in ("open_app", "web_search", "file_controller", "computer_control"):
        assert tool_name in names, f"expected tool '{tool_name}' still registered"

    repo_root = Path(__file__).resolve().parent.parent.parent
    main_py = (repo_root / "main.py").read_text(encoding="utf-8")
    assert "TOOL_DECLARATIONS" in main_py           # still present (now registry-generated)
    assert "_execute_tool" in main_py                # still present (now routes through the executor)
    assert "get_default_registry" in main_py
    assert "ToolExecutor" in main_py


def test_main_py_no_longer_constructs_genai_client_directly():
    """Confirms the Gemini Live session now goes through GeminiLiveAdapter,
    not a direct genai.Client()/aio.live.connect() call in main.py."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    main_py = (repo_root / "main.py").read_text(encoding="utf-8")
    assert "GeminiLiveAdapter" in main_py
    assert "genai.Client(" not in main_py
    assert "aio.live.connect(" not in main_py


def test_screen_processor_also_uses_live_adapter():
    repo_root = Path(__file__).resolve().parent.parent.parent
    sp = (repo_root / "actions" / "screen_processor.py").read_text(encoding="utf-8")
    assert "GeminiLiveAdapter" in sp
    assert "genai.Client(" not in sp
