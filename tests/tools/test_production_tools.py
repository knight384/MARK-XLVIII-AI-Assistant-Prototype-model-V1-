"""
tests/tools/test_production_tools.py — coverage for every tool wrapped in
core/tools/definitions.py. All underlying actions/*.py functions and JARVIS
runtime objects (ui, speak) are mocked — no real mouse movement, typing,
file deletion, messaging, browser, system settings changes, or code
execution happens here (Phase 3 spec, Part 33).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.tools.base import ToolContext
from core.tools.metadata import RiskLevel
from core.tools.registry import get_default_registry

REGISTRY = get_default_registry()


# -- registration / metadata sanity for every tool ---------------------

@pytest.mark.parametrize("tool_name", REGISTRY.list_names())
def test_every_tool_has_valid_metadata(tool_name):
    tool = REGISTRY.get(tool_name)
    assert tool is not None
    assert tool.name == tool_name
    assert tool.description
    assert isinstance(tool.metadata.risk_level, RiskLevel)
    assert tool.schema is not None


@pytest.mark.parametrize("tool_name", REGISTRY.list_names())
def test_every_tool_gemini_declaration_generates(tool_name):
    tool = REGISTRY.get(tool_name)
    decl = tool.gemini_declaration()
    assert decl["name"] == tool_name
    assert "parameters" in decl


def test_critical_risk_tools_are_the_expected_ones():
    """Matches the Phase 0 audit's security classification exactly."""
    critical = {t.name for t in REGISTRY.list() if t.metadata.risk_level == RiskLevel.CRITICAL}
    assert critical == {"desktop_control", "dev_agent"}


def test_high_risk_tools_are_the_expected_ones():
    high = {t.name for t in REGISTRY.list() if t.metadata.risk_level == RiskLevel.HIGH}
    assert high == {"browser_control", "file_controller", "code_helper", "computer_control"}


# -- mocked execution for each tool ------------------------------------

@pytest.mark.asyncio
async def test_open_app_tool_calls_underlying_function():
    with patch("actions.open_app.open_app", return_value="opened") as mock_fn:
        tool = REGISTRY.get("open_app")
        result = await tool.execute({"app_name": "Chrome"}, ToolContext(extra={"ui": MagicMock()}))
    assert result.success is True
    assert result.data == "opened"
    mock_fn.assert_called_once()


@pytest.mark.asyncio
async def test_weather_report_tool():
    with patch("actions.weather_report.weather_action", return_value="sunny, 72F"):
        tool = REGISTRY.get("weather_report")
        result = await tool.execute({"city": "SF"}, ToolContext(extra={"ui": MagicMock()}))
    assert result.success is True
    assert result.data == "sunny, 72F"


@pytest.mark.asyncio
async def test_browser_control_tool():
    with patch("actions.browser_control.browser_control", return_value="navigated"):
        tool = REGISTRY.get("browser_control")
        result = await tool.execute({"action": "go_to", "url": "https://example.com"},
                                     ToolContext(extra={"ui": MagicMock()}))
    assert result.success is True


@pytest.mark.asyncio
async def test_file_controller_tool():
    with patch("actions.file_controller.file_controller", return_value="listed"):
        tool = REGISTRY.get("file_controller")
        result = await tool.execute({"action": "list", "path": "desktop"},
                                     ToolContext(extra={"ui": MagicMock()}))
    assert result.success is True


@pytest.mark.asyncio
async def test_send_message_tool_default_message():
    with patch("actions.send_message.send_message", return_value=None):
        tool = REGISTRY.get("send_message")
        result = await tool.execute(
            {"receiver": "Bob", "message_text": "hi", "platform": "WhatsApp"},
            ToolContext(extra={"ui": MagicMock()}),
        )
    assert result.success is True
    assert "Bob" in result.data


@pytest.mark.asyncio
async def test_reminder_tool():
    with patch("actions.reminder.reminder", return_value="reminder set for tomorrow"):
        tool = REGISTRY.get("reminder")
        result = await tool.execute(
            {"date": "2026-01-01", "time": "09:00", "message": "call mom"},
            ToolContext(extra={"ui": MagicMock()}),
        )
    assert result.success is True


@pytest.mark.asyncio
async def test_youtube_video_tool():
    with patch("actions.youtube_video.youtube_video", return_value="playing"):
        tool = REGISTRY.get("youtube_video")
        result = await tool.execute({"action": "play", "query": "lofi"}, ToolContext(extra={"ui": MagicMock()}))
    assert result.success is True


@pytest.mark.asyncio
async def test_computer_settings_tool():
    with patch("actions.computer_settings.computer_settings", return_value="volume set"):
        tool = REGISTRY.get("computer_settings")
        result = await tool.execute({"action": "volume_set", "value": "50"}, ToolContext(extra={"ui": MagicMock()}))
    assert result.success is True


@pytest.mark.asyncio
async def test_desktop_control_tool_critical_risk_still_executes_via_mock():
    with patch("actions.desktop.desktop_control", return_value="wallpaper changed"):
        tool = REGISTRY.get("desktop_control")
        result = await tool.execute({"action": "wallpaper", "path": "x.jpg"}, ToolContext(extra={"ui": MagicMock()}))
    assert result.success is True
    assert tool.metadata.risk_level == RiskLevel.CRITICAL


@pytest.mark.asyncio
async def test_code_helper_tool():
    with patch("actions.code_helper.code_helper", return_value="code written"):
        tool = REGISTRY.get("code_helper")
        result = await tool.execute({"action": "write", "description": "hello world"},
                                     ToolContext(extra={"ui": MagicMock(), "speak": MagicMock()}))
    assert result.success is True


@pytest.mark.asyncio
async def test_dev_agent_tool():
    with patch("actions.dev_agent.dev_agent", return_value="project built"):
        tool = REGISTRY.get("dev_agent")
        result = await tool.execute({"description": "a todo app"},
                                     ToolContext(extra={"ui": MagicMock(), "speak": MagicMock()}))
    assert result.success is True


@pytest.mark.asyncio
async def test_web_search_tool_mirrors_to_ui_content_panel():
    ui = MagicMock()
    with patch("actions.web_search.web_search", return_value="Result: 42"):
        tool = REGISTRY.get("web_search")
        result = await tool.execute({"query": "answer to everything"}, ToolContext(extra={"ui": ui}))
    assert result.success is True
    ui.show_content.assert_called_once()


@pytest.mark.asyncio
async def test_web_search_tool_does_not_mirror_failed_search():
    ui = MagicMock()
    with patch("actions.web_search.web_search", return_value="No results found."):
        tool = REGISTRY.get("web_search")
        await tool.execute({"query": "xyzzy"}, ToolContext(extra={"ui": ui}))
    ui.show_content.assert_not_called()


@pytest.mark.asyncio
async def test_file_processor_tool_uses_current_file_when_no_path_given():
    ui = MagicMock()
    ui.current_file = "/tmp/uploaded.pdf"
    with patch("actions.file_processor.file_processor", return_value="summarized") as mock_fn:
        tool = REGISTRY.get("file_processor")
        result = await tool.execute({"action": "summarize"}, ToolContext(extra={"ui": ui, "speak": MagicMock()}))
    assert result.success is True
    called_args = mock_fn.call_args.kwargs["parameters"]
    assert called_args["file_path"] == "/tmp/uploaded.pdf"


@pytest.mark.asyncio
async def test_file_processor_tool_respects_explicit_path():
    ui = MagicMock()
    ui.current_file = "/tmp/should_not_use_this.pdf"
    with patch("actions.file_processor.file_processor", return_value="summarized") as mock_fn:
        tool = REGISTRY.get("file_processor")
        await tool.execute({"action": "summarize", "file_path": "/tmp/explicit.pdf"},
                            ToolContext(extra={"ui": ui, "speak": MagicMock()}))
    called_args = mock_fn.call_args.kwargs["parameters"]
    assert called_args["file_path"] == "/tmp/explicit.pdf"


@pytest.mark.asyncio
async def test_computer_control_tool():
    with patch("actions.computer_control.computer_control", return_value="clicked"):
        tool = REGISTRY.get("computer_control")
        result = await tool.execute({"action": "click", "x": 10, "y": 20}, ToolContext(extra={"ui": MagicMock()}))
    assert result.success is True


@pytest.mark.asyncio
async def test_game_updater_tool():
    with patch("actions.game_updater.game_updater", return_value="updating"):
        tool = REGISTRY.get("game_updater")
        result = await tool.execute({"action": "update"}, ToolContext(extra={"ui": MagicMock(), "speak": MagicMock()}))
    assert result.success is True


@pytest.mark.asyncio
async def test_flight_finder_tool():
    with patch("actions.flight_finder.flight_finder", return_value="found flights"):
        tool = REGISTRY.get("flight_finder")
        result = await tool.execute(
            {"origin": "SFO", "destination": "JFK", "date": "2026-01-01"},
            ToolContext(extra={"ui": MagicMock()}),
        )
    assert result.success is True


@pytest.mark.asyncio
async def test_system_status_tool():
    with patch("actions.system_monitor.get_system_status", return_value={"cpu": 10}):
        tool = REGISTRY.get("system_status")
        result = await tool.execute({}, ToolContext())
    assert result.success is True
    assert "cpu" in result.data


@pytest.mark.asyncio
async def test_save_memory_tool_is_silent():
    """Phase 5: save_memory now routes through core.memory's MemoryService
    (core.memory.get_default_memory_service().preferences.set(...)) instead
    of the legacy memory.memory_manager.update_memory — mock the new call path."""
    fake_service = MagicMock()
    with patch("core.memory.get_default_memory_service", return_value=fake_service):
        tool = REGISTRY.get("save_memory")
        result = await tool.execute(
            {"category": "identity", "key": "name", "value": "Vikram"}, ToolContext(),
        )
    assert result.success is True
    assert result.metadata.get("silent") is True
    fake_service.preferences.set.assert_called_once()


@pytest.mark.asyncio
async def test_save_memory_tool_skips_empty_key_or_value():
    fake_service = MagicMock()
    with patch("core.memory.get_default_memory_service", return_value=fake_service):
        tool = REGISTRY.get("save_memory")
        await tool.execute({"category": "identity", "key": "", "value": ""}, ToolContext())
    fake_service.preferences.set.assert_not_called()


@pytest.mark.asyncio
async def test_close_camera_tool():
    ui = MagicMock()
    tool = REGISTRY.get("close_camera")
    result = await tool.execute({}, ToolContext(extra={"ui": ui}))
    assert result.success is True
    ui.stop_camera_stream.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_jarvis_tool_speaks_goodbye():
    live = MagicMock()
    tool = REGISTRY.get("shutdown_jarvis")
    # Patch out the actual process-exit thread so the test suite doesn't die.
    with patch("core.tools.definitions.threading.Thread") as mock_thread:
        result = await tool.execute({}, ToolContext(extra={"live": live}))
    assert result.success is True
    live.speak.assert_called_once()
    mock_thread.assert_called_once()


@pytest.mark.asyncio
async def test_screen_process_tool_screen_capture():
    live = MagicMock()
    live._vision_busy = False
    live._vision_last_time = 0.0
    with patch("actions.screen_processor._capture_screen", return_value=(b"fakejpeg", "image/jpeg")):
        tool = REGISTRY.get("screen_process")
        result = await tool.execute({"angle": "screen", "text": "what is this"},
                                     ToolContext(extra={"live": live}))
    assert result.success is True
    assert "VISION_ACTIVE" in result.data
    assert live._pending_vision is not None


@pytest.mark.asyncio
async def test_screen_process_tool_respects_cooldown():
    import time
    live = MagicMock()
    live._vision_busy = False
    live._vision_last_time = time.monotonic()  # just happened — inside cooldown window
    tool = REGISTRY.get("screen_process")
    result = await tool.execute({"angle": "screen", "text": "what is this"}, ToolContext(extra={"live": live}))
    assert result.success is True
    assert "still processing" in result.data


@pytest.mark.asyncio
async def test_screen_process_tool_missing_live_context_fails_gracefully():
    tool = REGISTRY.get("screen_process")
    result = await tool.execute({"text": "what is this"}, ToolContext())  # no 'live' in extra
    assert result.success is False
