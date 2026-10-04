"""
core.tools.definitions — concrete Tool implementations (Phase 3 spec, Part 14).

Two patterns here:

1. **Standard action wrappers** (the majority): a thin Tool subclass whose
   `execute()` calls straight into the existing, unmodified
   `actions/*.py` function via `loop.run_in_executor`, exactly matching the
   arguments the old main.py dispatcher branch used to pass. No business
   logic is duplicated — this file is glue, not a reimplementation.

2. **JARVIS-runtime-coupled tools** (save_memory, screen_process,
   close_camera, shutdown_jarvis, web_search's UI-mirror behavior,
   file_processor's default-path injection): these replicate the exact
   special-case logic that used to live inline in main.py's dispatcher,
   using `context.extra["live"]` to reach the JarvisLive instance (ui,
   speak, in-session vision-cooldown state) they depend on. This preserves
   behavior byte-for-byte without inventing new session-state abstractions
   that belong to a later phase (Mission/session system).

Risk levels are seeded directly from the Phase 0 security audit.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time as _time

from .base import Tool, ToolContext
from .metadata import Capability as Cap
from .metadata import RiskLevel as Risk
from .metadata import ToolCategory as Cat
from .metadata import ToolMetadata
from .results import ToolResult
from .schemas import ParamSchema as P
from .schemas import ToolSchema

logger = logging.getLogger(__name__)


async def _run_sync(fn):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn)


# ============================================================================
# Standard action wrappers
# ============================================================================

class OpenAppTool(Tool):
    name = "open_app"
    description = (
        "Opens any application on the computer. "
        "Use this whenever the user asks to open, launch, or start any app, "
        "website, or program. Always call this tool — never just say you opened it."
    )
    schema = ToolSchema((
        P("app_name", "string", "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')", required=True),
    ))
    metadata = ToolMetadata(category=Cat.SYSTEM, risk_level=Risk.MEDIUM,
                             capabilities=(Cap.PROCESS_EXECUTION,), timeout_seconds=20)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.open_app import open_app
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: open_app(parameters=args, response=None, player=ui))
        return ToolResult.ok(self.name, data=r or f"Opened {args.get('app_name')}.")


class WeatherReportTool(Tool):
    name = "weather_report"
    description = "Gives the weather report to user"
    schema = ToolSchema((P("city", "string", "City name", required=True),))
    metadata = ToolMetadata(category=Cat.WEB, risk_level=Risk.LOW,
                             capabilities=(Cap.NETWORK,), timeout_seconds=20)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.weather_report import weather_action
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: weather_action(parameters=args, player=ui))
        return ToolResult.ok(self.name, data=r or "Weather delivered.")


class BrowserControlTool(Tool):
    name = "browser_control"
    description = (
        "Controls any web browser. Use for: opening websites, searching the web, "
        "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
        "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
        "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
    )
    schema = ToolSchema((
        P("action", "string",
          "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | "
          "get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | "
          "list_browsers | close | close_all", required=True),
        P("browser", "string", "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari."),
        P("url", "string", "URL for go_to / new_tab action"),
        P("query", "string", "Search query for search action"),
        P("engine", "string", "Search engine: google | bing | duckduckgo | yandex (default: google)"),
        P("selector", "string", "CSS selector for click/type"),
        P("text", "string", "Text to click or type"),
        P("description", "string", "Element description for smart_click/smart_type"),
        P("direction", "string", "up | down for scroll"),
        P("amount", "integer", "Scroll amount in pixels (default: 500)"),
        P("key", "string", "Key name for press action (e.g. Enter, Escape, F5)"),
        P("path", "string", "Save path for screenshot"),
        P("incognito", "boolean", "Open in private/incognito mode"),
        P("clear_first", "boolean", "Clear field before typing (default: true)"),
        P("use_real_profile", "boolean",
          "Use the user's real, authenticated browser profile (existing logins/sessions) instead of "
          "the isolated JARVIS profile. Default false — only set true when the task genuinely needs "
          "an existing authenticated session. This is visible to the approval prompt (Phase 6)."),
    ))
    metadata = ToolMetadata(category=Cat.BROWSER, risk_level=Risk.HIGH,
                             capabilities=(Cap.BROWSER_CONTROL, Cap.NETWORK), timeout_seconds=45,
                             notes="Persistent background browser session — the executor's per-call "
                                   "timeout does not tear down the session, only this single action. "
                                   "Phase 6: uses an isolated JARVIS browser profile by default; the "
                                   "user's real authenticated profile requires explicit "
                                   "use_real_profile=true (still subject to the same mandatory HIGH-risk "
                                   "policy approval as every browser_control call).")

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.browser_control import browser_control
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: browser_control(parameters=args, player=ui))
        return ToolResult.ok(self.name, data=r or "Done.")


class FileControllerTool(Tool):
    name = "file_controller"
    description = "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage."
    schema = ToolSchema((
        P("action", "string",
          "list | create_file | create_folder | delete | move | copy | rename | read | write | find | "
          "largest | disk_usage | organize_desktop | info", required=True),
        P("path", "string", "File/folder path or shortcut: desktop, downloads, documents, home"),
        P("destination", "string", "Destination path for move/copy"),
        P("new_name", "string", "New name for rename"),
        P("content", "string", "Content for create_file/write"),
        P("name", "string", "File name to search for"),
        P("extension", "string", "File extension to search (e.g. .pdf)"),
        P("count", "integer", "Number of results for largest"),
    ))
    metadata = ToolMetadata(category=Cat.FILESYSTEM, risk_level=Risk.HIGH,
                             capabilities=(Cap.READ, Cap.WRITE, Cap.FILESYSTEM), timeout_seconds=30)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.file_controller import file_controller
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: file_controller(parameters=args, player=ui))
        return ToolResult.ok(self.name, data=r or "Done.")


class SendMessageTool(Tool):
    name = "send_message"
    description = "Sends a text message via WhatsApp, Telegram, or other messaging platform."
    schema = ToolSchema((
        P("receiver", "string", "Recipient contact name", required=True),
        P("message_text", "string", "The message to send", required=True),
        P("platform", "string", "Platform: WhatsApp, Telegram, etc.", required=True),
    ))
    metadata = ToolMetadata(category=Cat.COMMUNICATION, risk_level=Risk.MEDIUM,
                             capabilities=(Cap.COMPUTER_CONTROL, Cap.NETWORK), timeout_seconds=30)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.send_message import send_message
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: send_message(parameters=args, response=None, player=ui, session_memory=None))
        return ToolResult.ok(self.name, data=r or f"Message sent to {args.get('receiver')}.")


class ReminderTool(Tool):
    name = "reminder"
    description = "Sets a timed reminder using Task Scheduler."
    schema = ToolSchema((
        P("date", "string", "Date in YYYY-MM-DD format", required=True),
        P("time", "string", "Time in HH:MM format (24h)", required=True),
        P("message", "string", "Reminder message text", required=True),
    ))
    metadata = ToolMetadata(category=Cat.PRODUCTIVITY, risk_level=Risk.LOW, timeout_seconds=15)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.reminder import reminder
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: reminder(parameters=args, response=None, player=ui))
        return ToolResult.ok(self.name, data=r or "Reminder set.")


class YoutubeVideoTool(Tool):
    name = "youtube_video"
    description = (
        "Controls YouTube. Use for: playing videos, summarizing a video's content, "
        "getting video info, or showing trending videos."
    )
    schema = ToolSchema((
        P("action", "string", "play | summarize | get_info | trending (default: play)"),
        P("query", "string", "Search query for play action"),
        P("save", "boolean", "Save summary to Notepad (summarize only)"),
        P("region", "string", "Country code for trending e.g. TR, US"),
        P("url", "string", "Video URL for get_info action"),
    ))
    metadata = ToolMetadata(category=Cat.MEDIA, risk_level=Risk.MEDIUM,
                             capabilities=(Cap.NETWORK,), timeout_seconds=45)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.youtube_video import youtube_video
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: youtube_video(parameters=args, response=None, player=ui))
        return ToolResult.ok(self.name, data=r or "Done.")


class ComputerSettingsTool(Tool):
    name = "computer_settings"
    description = (
        "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
        "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
        "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
        "Use for ANY single computer control command."
    )
    schema = ToolSchema((
        P("action", "string", "The action to perform"),
        P("description", "string", "Natural language description of what to do"),
        P("value", "string", "Optional value: volume level, text to type, etc."),
    ))
    metadata = ToolMetadata(category=Cat.COMPUTER, risk_level=Risk.MEDIUM,
                             capabilities=(Cap.COMPUTER_CONTROL,), timeout_seconds=20)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.computer_settings import computer_settings
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: computer_settings(parameters=args, response=None, player=ui))
        return ToolResult.ok(self.name, data=r or "Done.")


class DesktopControlTool(Tool):
    name = "desktop_control"
    description = "Controls the desktop: wallpaper, organize, clean, list, stats."
    schema = ToolSchema((
        P("action", "string", "wallpaper | wallpaper_url | organize | clean | list | stats | task", required=True),
        P("path", "string", "Image path for wallpaper"),
        P("url", "string", "Image URL for wallpaper_url"),
        P("mode", "string", "by_type or by_date for organize"),
        P("task", "string", "Natural language desktop task"),
    ))
    # Phase 6 finding, documented rather than papered over: the "task" action
    # generates code that controls the HOST GUI directly (pyautogui mouse/
    # keyboard, window management, registry reads via ctypes/winreg). This is
    # structurally incompatible with Docker-style sandboxing — a container has
    # no access to the host's display/input devices, so containing this code
    # would break the feature entirely, not secure it (spec Part 67: no
    # security theater — don't claim isolation that isn't real).
    # requires_sandbox stays False for exactly this reason. The actual
    # safeguard is CRITICAL risk -> mandatory PolicyEngine approval on every
    # single call, with the generated task description visible in the
    # approval prompt (via ToolExecutor's argument summary) for the user to
    # review before granting. The exec() call itself keeps its prior
    # restricted-builtins allowlist as defense-in-depth, but per Phase 0/6
    # findings that allowlist is NOT treated as a security boundary — see
    # SECURITY.md.
    metadata = ToolMetadata(category=Cat.COMPUTER, risk_level=Risk.CRITICAL,
                             capabilities=(Cap.COMPUTER_CONTROL, Cap.CODE_EXECUTION, Cap.FILESYSTEM),
                             timeout_seconds=60, requires_sandbox=False,
                             notes="'task' action executes LLM-generated code via exec() to control the "
                                   "HOST GUI directly — this cannot be Docker-sandboxed without breaking "
                                   "the feature (no container access to host display/input). Real "
                                   "protection is mandatory per-call human approval (CRITICAL risk), not "
                                   "code isolation. See SECURITY.md / docs/security-model.md.")

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.desktop import desktop_control
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: desktop_control(parameters=args, player=ui))
        return ToolResult.ok(self.name, data=r or "Done.")


class CodeHelperTool(Tool):
    name = "code_helper"
    description = "Writes, edits, explains, runs, or builds code files."
    schema = ToolSchema((
        P("action", "string", "write | edit | explain | run | build | auto (default: auto)"),
        P("description", "string", "What the code should do or what change to make"),
        P("language", "string", "Programming language (default: python)"),
        P("output_path", "string", "Where to save the file"),
        P("file_path", "string", "Path to existing file for edit/explain/run/build"),
        P("code", "string", "Raw code string for explain"),
        P("args", "string", "CLI arguments for run/build"),
        P("timeout", "integer", "Execution timeout in seconds (default: 30)"),
    ))
    metadata = ToolMetadata(category=Cat.DEVELOPER, risk_level=Risk.HIGH,
                             capabilities=(Cap.CODE_EXECUTION, Cap.FILESYSTEM, Cap.PROCESS_EXECUTION),
                             timeout_seconds=90)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.code_helper import code_helper
        ui = context.extra.get("ui")
        speak = context.extra.get("speak")
        r = await _run_sync(lambda: code_helper(parameters=args, player=ui, speak=speak))
        return ToolResult.ok(self.name, data=r or "Done.")


class DevAgentTool(Tool):
    name = "dev_agent"
    description = "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors."
    schema = ToolSchema((
        P("description", "string", "What the project should do", required=True),
        P("language", "string", "Programming language (default: python)"),
        P("project_name", "string", "Optional project folder name"),
        P("timeout", "integer", "Run timeout in seconds (default: 30)"),
    ))
    # Phase 6: the model-planned run command (actions/dev_agent.py::_run_project)
    # now executes through core.sandbox.SandboxManager — Docker when available,
    # a clearly-documented-as-weaker host-restricted fallback for HIGH-and-below,
    # and a refusal for CRITICAL if neither is acceptable (see
    # core/sandbox/manager.py's _FALLBACK_ACCEPTABLE_FOR). requires_sandbox=True
    # tells the PolicyEngine to deny outright if no sandbox is available at all
    # for this risk level, rather than silently falling back to an unsandboxed
    # host run. Every call additionally requires policy approval (CRITICAL).
    metadata = ToolMetadata(category=Cat.DEVELOPER, risk_level=Risk.CRITICAL,
                             capabilities=(Cap.CODE_EXECUTION, Cap.FILESYSTEM, Cap.PROCESS_EXECUTION, Cap.NETWORK),
                             timeout_seconds=180, requires_sandbox=True,
                             notes="Model-planned run command executes via SandboxManager (Phase 6) — "
                                   "Docker when available, else a documented-weaker host-restricted "
                                   "fallback for non-CRITICAL sandbox risk, or refusal. Dependency "
                                   "install (pip) still runs on host into the project directory "
                                   "itself (installing into an isolated sandbox wouldn't leave the "
                                   "packages where the project can use them) — gated by the same "
                                   "mandatory CRITICAL-risk policy approval as everything else here.")

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.dev_agent import dev_agent
        from core.sandbox import get_default_sandbox_manager
        ui = context.extra.get("ui")
        speak = context.extra.get("speak")
        sandbox_manager = get_default_sandbox_manager()
        r = await _run_sync(lambda: dev_agent(parameters=args, player=ui, speak=speak,
                                               sandbox_manager=sandbox_manager))
        return ToolResult.ok(self.name, data=r or "Done.")


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Searches the web. Use for ANY question about current facts, events, prices, "
        "or topics — always prefer this over guessing. "
        "Modes: 'search' (default), 'news' (latest headlines on a topic), "
        "'research' (deep comprehensive answer), 'price' (product cost lookup), "
        "'compare' (side-by-side comparison of items)."
    )
    schema = ToolSchema((
        P("query", "string", "Search query or topic", required=True),
        P("mode", "string", "search | news | research | price | compare"),
        P("items", "array", "Items to compare (compare mode)", items_type="string"),
        P("aspect", "string", "Comparison aspect: price | specs | reviews | features"),
    ))
    metadata = ToolMetadata(category=Cat.WEB, risk_level=Risk.LOW,
                             capabilities=(Cap.NETWORK,), timeout_seconds=45)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.web_search import web_search as web_search_action
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: web_search_action(parameters=args, player=ui))
        result = r or "Done."

        # Preserves main.py's prior behavior of mirroring results to the
        # on-screen content panel.
        if ui is not None:
            mode = args.get("mode", "search")
            if r and not r.startswith("No results") and not r.startswith("Search failed"):
                query = args.get("query") or ", ".join(args.get("items", []))
                label = f"{mode.upper()} — {query[:38]}" if query else mode.upper()
                ui.show_content(label, r)

        return ToolResult.ok(self.name, data=result)


class FileProcessorTool(Tool):
    name = "file_processor"
    description = (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    )
    schema = ToolSchema((
        P("file_path", "string", "Full path to the uploaded file. Leave empty to use the currently uploaded file."),
        P("action", "string", "What to do with the file (varies by type — see description)."),
        P("instruction", "string", "Free-form instruction if action doesn't cover it."),
        P("format", "string", "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"),
        P("width", "integer", "Target width for image resize"),
        P("height", "integer", "Target height for image resize"),
        P("scale", "number", "Scale factor for image resize (e.g. 0.5)"),
        P("quality", "integer", "Quality 1-100 for image/video compress"),
        P("start", "string", "Start time for trim: seconds or HH:MM:SS"),
        P("end", "string", "End time for trim: seconds or HH:MM:SS"),
        P("timestamp", "string", "Timestamp for video frame extraction HH:MM:SS"),
        P("column", "string", "Column name for CSV filter/sort"),
        P("value", "string", "Filter value for CSV filter"),
        P("condition", "string", "Filter condition: equals|contains|gt|lt"),
        P("ascending", "boolean", "Sort order for CSV sort (default: true)"),
        P("save", "boolean", "Save result to file (default: true)"),
        P("destination", "string", "Output folder for archive extract"),
    ))
    # Preserves vision/image behavior exactly (spec Part 29: "Do not force
    # vision requests through the generic text model abstraction") — this
    # tool wrapper doesn't touch that at all, it just calls the unmodified
    # file_processor() function, which (as of Phase 2) already routes its
    # own text-only Gemini calls through the Gateway while keeping direct
    # SDK calls for image/vision content.
    metadata = ToolMetadata(category=Cat.FILESYSTEM, risk_level=Risk.MEDIUM,
                             capabilities=(Cap.READ, Cap.WRITE, Cap.FILESYSTEM), timeout_seconds=60)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.file_processor import file_processor
        ui = context.extra.get("ui")
        speak = context.extra.get("speak")

        # Preserves main.py's prior default-file-path injection.
        if not args.get("file_path") and ui is not None and getattr(ui, "current_file", None):
            args = {**args, "file_path": ui.current_file}

        r = await _run_sync(lambda: file_processor(parameters=args, player=ui, speak=speak))
        return ToolResult.ok(self.name, data=r or "Done.")


class ComputerControlTool(Tool):
    name = "computer_control"
    description = "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen."
    schema = ToolSchema((
        P("action", "string",
          "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | "
          "copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | "
          "random_data | user_data", required=True),
        P("text", "string", "Text to type or paste"),
        P("x", "integer", "X coordinate"),
        P("y", "integer", "Y coordinate"),
        P("keys", "string", "Key combination e.g. 'ctrl+c'"),
        P("key", "string", "Single key e.g. 'enter'"),
        P("direction", "string", "up | down | left | right"),
        P("amount", "integer", "Scroll amount (default: 3)"),
        P("seconds", "number", "Seconds to wait"),
        P("title", "string", "Window title for focus_window"),
        P("description", "string", "Element description for screen_find/screen_click"),
        P("type", "string", "Data type for random_data"),
        P("field", "string", "Field for user_data: name|email|city"),
        P("clear_first", "boolean", "Clear field before typing (default: true)"),
        P("path", "string", "Save path for screenshot"),
    ))
    metadata = ToolMetadata(category=Cat.COMPUTER, risk_level=Risk.HIGH,
                             capabilities=(Cap.COMPUTER_CONTROL,), timeout_seconds=20,
                             notes="Sends real mouse/keyboard input. Cancellation not safe mid-gesture.")

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.computer_control import computer_control
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: computer_control(parameters=args, player=ui))
        return ToolResult.ok(self.name, data=r or "Done.")


class GameUpdaterTool(Tool):
    name = "game_updater"
    description = (
        "THE ONLY tool for ANY Steam or Epic Games request. "
        "Use for: installing, downloading, updating games, listing installed games, "
        "checking download status, scheduling updates. "
        "ALWAYS call directly for any Steam/Epic/game request. "
        "NEVER use browser_control or web_search for Steam/Epic."
    )
    schema = ToolSchema((
        P("action", "string", "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"),
        P("platform", "string", "steam | epic | both (default: both)"),
        P("game_name", "string", "Game name (partial match supported)"),
        P("app_id", "string", "Steam AppID for install (optional)"),
        P("hour", "integer", "Hour for scheduled update 0-23 (default: 3)"),
        P("minute", "integer", "Minute for scheduled update 0-59 (default: 0)"),
        P("shutdown_when_done", "boolean", "Shut down PC when download finishes"),
    ))
    metadata = ToolMetadata(category=Cat.SYSTEM, risk_level=Risk.MEDIUM,
                             capabilities=(Cap.NETWORK, Cap.PROCESS_EXECUTION), timeout_seconds=30)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.game_updater import game_updater
        ui = context.extra.get("ui")
        speak = context.extra.get("speak")
        r = await _run_sync(lambda: game_updater(parameters=args, player=ui, speak=speak))
        return ToolResult.ok(self.name, data=r or "Done.")


class FlightFinderTool(Tool):
    name = "flight_finder"
    description = "Searches Google Flights and speaks the best options."
    schema = ToolSchema((
        P("origin", "string", "Departure city or airport code", required=True),
        P("destination", "string", "Arrival city or airport code", required=True),
        P("date", "string", "Departure date (any format)", required=True),
        P("return_date", "string", "Return date for round trips"),
        P("passengers", "integer", "Number of passengers (default: 1)"),
        P("cabin", "string", "economy | premium | business | first"),
        P("save", "boolean", "Save results to Notepad"),
    ))
    metadata = ToolMetadata(category=Cat.PRODUCTIVITY, risk_level=Risk.LOW,
                             capabilities=(Cap.NETWORK,), timeout_seconds=45)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.flight_finder import flight_finder
        ui = context.extra.get("ui")
        r = await _run_sync(lambda: flight_finder(parameters=args, player=ui))
        return ToolResult.ok(self.name, data=r or "Done.")


class SystemStatusTool(Tool):
    name = "system_status"
    description = (
        "Returns real-time system metrics: CPU usage, RAM, GPU load, CPU temperature, "
        "uptime, and process count. Use when the user asks about computer performance, "
        "temperature, memory, or resource usage."
    )
    schema = ToolSchema()
    metadata = ToolMetadata(category=Cat.SYSTEM, risk_level=Risk.LOW, timeout_seconds=10)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.system_monitor import get_system_status
        r = await _run_sync(get_system_status)
        return ToolResult.ok(self.name, data=str(r))


# ============================================================================
# JARVIS-runtime-coupled tools (need context.extra["live"])
# ============================================================================

class SaveMemoryTool(Tool):
    name = "save_memory"
    description = (
        "Save an important personal fact about the user to long-term memory. "
        "Call this silently whenever the user reveals something worth remembering: "
        "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
        "Do NOT call for: weather, reminders, searches, or one-time commands. "
        "Do NOT announce that you are saving — just call it silently. "
        "Values must be in English regardless of the conversation language."
    )
    schema = ToolSchema((
        P("category", "string",
          "identity | preferences | projects | relationships | wishes | notes", required=True),
        P("key", "string", "Short snake_case key (e.g. name, favorite_food, sister_name)", required=True),
        P("value", "string", "Concise value in English (e.g. Fatih, pizza, older sister)", required=True),
    ))
    metadata = ToolMetadata(category=Cat.MEMORY, risk_level=Risk.LOW,
                             capabilities=(Cap.WRITE,), timeout_seconds=10)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from core.memory import get_default_memory_service
        from core.memory.models import Source
        category = args.get("category", "notes")
        key = args.get("key", "")
        value = args.get("value", "")
        if key and value:
            get_default_memory_service().preferences.set(category, key, value, source=Source.USER)
            logger.info(f"[Memory] save_memory: {category}/{key} saved")  # Phase 5: value itself never logged
        # Matches the prior dispatcher's silent, non-spoken response shape.
        return ToolResult.ok(self.name, data="ok", metadata={"silent": True})


class ScreenProcessTool(Tool):
    name = "screen_process"
    description = (
        "Captures the screen or webcam image and lets you analyze it. "
        "MUST be called when user asks what is on screen, what you see, "
        "look at camera, analyze my screen, etc. "
        "You have NO visual ability without this tool. "
        "After the image is captured it is sent directly to you — describe what you see and answer the user's question. "
        "When using camera: the live view stays open until user says close it or calls close_camera."
    )
    schema = ToolSchema((
        P("angle", "string", "'screen' to capture display, 'camera' for webcam. Default: 'screen'"),
        P("text", "string", "The question or instruction about the captured image", required=True),
    ))
    metadata = ToolMetadata(category=Cat.VISION, risk_level=Risk.MEDIUM,
                             capabilities=(Cap.CAMERA,), timeout_seconds=15,
                             notes="Requires context.extra['live'] (JarvisLive instance) for in-session "
                                   "vision-cooldown state and camera-stream UI control.")

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from actions.screen_processor import _capture_camera, _capture_screen
        live = context.extra.get("live")
        if live is None:
            return ToolResult.fail(self.name, error="No JarvisLive session context available.",
                                    error_type="ToolExecutionError")

        now = _time.monotonic()
        cooldown = 4.0  # seconds — covers echo window after speaking ends
        if live._vision_busy or (now - live._vision_last_time) < cooldown:
            wait = max(0, cooldown - (now - live._vision_last_time))
            logger.info(f"[Vision] Cooldown active ({wait:.1f}s remaining) — ignoring duplicate call")
            return ToolResult.ok(self.name, data="Vision is still processing the previous request. I will not call this again.")

        live._vision_busy = True
        live._vision_last_time = now
        angle = args.get("angle", "screen").lower()
        user_text = args.get("text", "What do you see?")

        if angle == "camera":
            img_b, mime_t = await _run_sync(_capture_camera)
            live.ui.start_camera_stream()
            live._vision_cam_active = True
            logger.info(f"[Vision] Camera: {len(img_b):,} bytes")
            stall = "camera"
        else:
            img_b, mime_t = await _run_sync(_capture_screen)
            logger.info(f"[Vision] Screen: {len(img_b):,} bytes")
            stall = "screen"

        live._pending_vision = (img_b, mime_t, user_text, angle)
        message = (
            f"[VISION_ACTIVE] {stall.capitalize()} captured. "
            f"Immediately say ONE natural sentence in the user's language "
            f"(e.g. 'Looking at your {stall} now, sir' / "
            f"'{'Kameraya' if stall == 'camera' else 'Ekrana'} bakıyorum efendim'). "
            f"Do NOT describe or guess content — the actual image arrives in the NEXT message."
        )
        return ToolResult.ok(self.name, data=message)


class CloseCameraTool(Tool):
    name = "close_camera"
    description = (
        "Closes the live camera view shown on screen. "
        "Call when user says: close camera, stop camera, turn off camera, "
        "kamerayı kapat, kapat, creepy, etc."
    )
    schema = ToolSchema()
    metadata = ToolMetadata(category=Cat.VISION, risk_level=Risk.LOW, timeout_seconds=5)

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        ui = context.extra.get("ui")
        if ui is not None:
            ui.stop_camera_stream()
        return ToolResult.ok(self.name, data="Camera closed.")


class ShutdownJarvisTool(Tool):
    name = "shutdown_jarvis"
    description = (
        "Shuts down the assistant completely. "
        "Call this when the user expresses intent to end the conversation, "
        "close the assistant, say goodbye, or stop Jarvis. "
        "The user can say this in ANY language."
    )
    schema = ToolSchema()
    metadata = ToolMetadata(category=Cat.SYSTEM, risk_level=Risk.MEDIUM,
                             capabilities=(Cap.PROCESS_EXECUTION,), timeout_seconds=5,
                             notes="Terminates the process via os._exit(0) on a daemon thread — matches "
                                   "prior main.py behavior exactly.")

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        live = context.extra.get("live")
        if live is not None:
            live.ui.write_log("SYS: Shutdown requested.")
            live.speak("Goodbye, sir.")

        def _shutdown():
            import os
            _time.sleep(1)
            os._exit(0)

        threading.Thread(target=_shutdown, daemon=True).start()
        return ToolResult.ok(self.name, data="Shutting down.")


# ============================================================================
# Registration
# ============================================================================

def register_all_tools(registry) -> None:
    """Registers every production tool. This is the single canonical list —
    see docs/tools.md for the human-readable version."""
    tools = [
        OpenAppTool(), WeatherReportTool(), BrowserControlTool(), FileControllerTool(),
        SendMessageTool(), ReminderTool(), YoutubeVideoTool(), ComputerSettingsTool(),
        DesktopControlTool(), CodeHelperTool(), DevAgentTool(), WebSearchTool(),
        FileProcessorTool(), ComputerControlTool(), GameUpdaterTool(), FlightFinderTool(),
        SystemStatusTool(), SaveMemoryTool(), ScreenProcessTool(), CloseCameraTool(),
        ShutdownJarvisTool(),
    ]
    for tool in tools:
        registry.register(tool)
