"""tests/tools/test_registry.py"""
from __future__ import annotations

import pytest
from .conftest import EchoTool, FailingTool

from core.tools.errors import ToolRegistrationError


def test_register_and_get(empty_registry):
    tool = EchoTool()
    empty_registry.register(tool)
    assert empty_registry.get("echo_tool") is tool


def test_duplicate_name_raises(empty_registry):
    empty_registry.register(EchoTool())
    with pytest.raises(ToolRegistrationError):
        empty_registry.register(EchoTool())


def test_get_missing_returns_none(empty_registry):
    assert empty_registry.get("nonexistent") is None


def test_exists(empty_registry):
    empty_registry.register(EchoTool())
    assert empty_registry.exists("echo_tool") is True
    assert empty_registry.exists("nonexistent") is False


def test_list_and_list_names(empty_registry):
    empty_registry.register(EchoTool())
    empty_registry.register(FailingTool())
    assert len(empty_registry.list()) == 2
    assert set(empty_registry.list_names()) == {"echo_tool", "failing_tool"}


def test_unregister(empty_registry):
    empty_registry.register(EchoTool())
    empty_registry.unregister("echo_tool")
    assert empty_registry.get("echo_tool") is None


def test_alias_lookup(empty_registry):
    tool = EchoTool()
    empty_registry.register(tool, aliases=("echo", "say"))
    assert empty_registry.get("echo") is tool
    assert empty_registry.get("say") is tool
    assert empty_registry.get("echo_tool") is tool


def test_alias_conflict_raises(empty_registry):
    empty_registry.register(EchoTool(), aliases=("echo",))
    with pytest.raises(ToolRegistrationError):
        empty_registry.register(FailingTool(), aliases=("echo",))


def test_list_by_category(empty_registry):
    from core.tools.metadata import ToolCategory
    empty_registry.register(EchoTool())
    tools = empty_registry.list_by_category(ToolCategory.SYSTEM)
    assert len(tools) == 1
    assert tools[0].name == "echo_tool"


def test_generate_gemini_declarations(empty_registry):
    empty_registry.register(EchoTool())
    decls = empty_registry.generate_gemini_declarations()
    assert len(decls) == 1
    assert decls[0]["name"] == "echo_tool"


def test_default_registry_has_all_production_tools():
    from core.tools.registry import get_default_registry
    registry = get_default_registry()
    expected = {
        "open_app", "web_search", "system_status", "weather_report", "send_message",
        "reminder", "youtube_video", "screen_process", "close_camera", "computer_settings",
        "browser_control", "file_controller", "desktop_control", "code_helper", "dev_agent",
        "computer_control", "game_updater", "flight_finder", "shutdown_jarvis",
        "file_processor", "save_memory",
    }
    assert set(registry.list_names()) == expected
