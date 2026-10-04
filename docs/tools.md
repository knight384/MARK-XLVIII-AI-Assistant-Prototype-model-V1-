# Registered Tools

21 tools, all registered in `core/tools/definitions.py::register_all_tools()`.
Names are unchanged from the pre-Phase-3 Gemini function declarations — no
renames, no aliases needed.

Timeout/cancellation column key (Phase 3 spec, Part 20):
**SUPPORTED** = the executor's timeout cleanly aborts waiting without side
effects · **LIMITED** = a timeout can fire mid-operation, leaving partial
state (documented per-tool) · **NOT SAFE** = do not rely on the timeout to
mean "nothing happened" for that call.

| Tool | Category | Risk | Capabilities | Timeout(s) | Cancellation | Implementation |
|---|---|---|---|---|---|---|
| `open_app` | computer | MEDIUM | process_execution | 20 | LIMITED — app may still launch after timeout fires | `actions/open_app.py` |
| `weather_report` | web | LOW | network | 20 | SUPPORTED | `actions/weather_report.py` |
| `browser_control` | browser | HIGH | browser_control, network | 45 | LIMITED — persistent background session isn't torn down by a single call's timeout | `actions/browser_control.py` |
| `file_controller` | filesystem | HIGH | read, write, filesystem | 30 | NOT SAFE — delete/move/rename can partially complete | `actions/file_controller.py` |
| `send_message` | communication | MEDIUM | computer_control, network | 30 | NOT SAFE — message may have already been sent via OS automation | `actions/send_message.py` |
| `reminder` | productivity | LOW | — | 15 | SUPPORTED | `actions/reminder.py` |
| `youtube_video` | media | MEDIUM | network | 45 | LIMITED | `actions/youtube_video.py` |
| `screen_process` | vision | MEDIUM | camera | 15 | LIMITED — camera stream may stay open | `actions/screen_processor.py` (dispatch logic in `ScreenProcessTool`) |
| `close_camera` | vision | LOW | — | 5 | SUPPORTED | UI call only |
| `computer_settings` | computer | MEDIUM | computer_control | 20 | NOT SAFE — OS setting may already be changed | `actions/computer_settings.py` |
| `desktop_control` | computer | **CRITICAL** | computer_control, code_execution, filesystem | 60 | NOT SAFE | `actions/desktop.py` — LLM-generated code via `exec()`, controls the host GUI directly so it **cannot** be Docker-sandboxed (Phase 6 finding); real protection is mandatory per-call approval, see `docs/security-model.md` |
| `code_helper` | developer | HIGH | code_execution, filesystem, process_execution | 90 | NOT SAFE | `actions/code_helper.py` |
| `dev_agent` | developer | **CRITICAL** | code_execution, filesystem, process_execution, network | 180 | NOT SAFE — model-planned run command now executes via SandboxManager (Phase 6); dependency install still runs on host | `actions/dev_agent.py`, sandboxed as of Phase 6 (see `docs/sandbox.md`) |
| `web_search` | web | LOW | network | 45 | SUPPORTED | `actions/web_search.py`, mirrors results to the UI content panel |
| `file_processor` | filesystem | MEDIUM | read, write, filesystem | 60 | LIMITED — file conversion/write may partially complete | `actions/file_processor.py` |
| `computer_control` | computer | HIGH | computer_control | 20 | NOT SAFE — sends real mouse/keyboard input mid-gesture | `actions/computer_control.py` |
| `game_updater` | system | MEDIUM | network, process_execution | 30 | LIMITED | `actions/game_updater.py` |
| `flight_finder` | productivity | LOW | network | 45 | SUPPORTED | `actions/flight_finder.py` |
| `system_status` | system | LOW | — | 10 | SUPPORTED | `actions/system_monitor.py::get_system_status` |
| `save_memory` | memory | LOW | write | 10 | SUPPORTED | `memory/memory_manager.py::update_memory`; silent response (no spoken confirmation) |
| `shutdown_jarvis` | system | MEDIUM | process_execution | 5 | NOT SAFE — terminates the process via `os._exit(0)` | Special-cased in `ShutdownJarvisTool` |

## Risk classification summary

- **CRITICAL** (2): `desktop_control`, `dev_agent` — both execute
  LLM-generated or agent-planned code/commands without sandboxing. See
  `SECURITY.md` and the Phase 0 audit.
- **HIGH** (4): `browser_control`, `file_controller`, `code_helper`,
  `computer_control`.
- **MEDIUM** (8): `open_app`, `send_message`, `youtube_video`,
  `screen_process`, `computer_settings`, `file_processor`, `game_updater`,
  `shutdown_jarvis`.
- **LOW** (7): `weather_report`, `reminder`, `close_camera`, `web_search`,
  `flight_finder`, `system_status`, `save_memory`.

## Verification/dry-run support

No production tool currently sets `supports_verification=True` or
`supports_dry_run=True` — the hooks exist in the `Tool`/`ToolExecutor`
interface (see `docs/architecture/tool-system.md`) and are tested with a
synthetic tool (`tests/tools/test_executor.py`), but no real tool opts in
yet. A future phase can add verification to, e.g., `file_controller`
(check the file actually exists/was deleted after the call) without
changing the Executor.

## Adding a tool

See `DEVELOPMENT.md`'s "Adding a new tool" section.
