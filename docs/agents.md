# Registered Agents

6 specialized agents plus the Orchestrator/Planner, registered in
`core/agent/agents.py::register_all_agents()`. See
`docs/architecture/multi-agent-runtime.md` for how they fit together.

## developer_agent — Developer Agent

- **Responsibility**: coding tasks — writing, editing, running, debugging
  code; building multi-file projects from scratch.
- **Capability**: `CODING`
- **Tools**: `dev_agent`, `code_helper`
- **Model requirements**: text generation, tool calling, reasoning
- **Max declared risk**: **CRITICAL** (the `dev_agent` tool executes
  unsandboxed subprocess commands including an automated fix-loop — see the
  Phase 0 audit and `docs/tools.md`)
- **Limitations**: does not sandbox execution (Phase 6 will); does not
  reimplement `actions/dev_agent.py`'s internal plan/write/run/fix loop —
  wraps it at the orchestration layer only.

## research_agent — Research Agent

- **Responsibility**: information gathering — web search, weather, flight
  lookups.
- **Capability**: `RESEARCH`
- **Tools**: `web_search`, `weather_report`, `flight_finder`
- **Model requirements**: text generation, tool calling
- **Max declared risk**: LOW
- **Limitations**: no filesystem, browser, or computer-control access — a
  research task requiring those delegates to a different agent via a
  separate plan step.

## browser_agent — Browser Agent

- **Responsibility**: browser-based interaction — navigation, search,
  clicking, form-filling.
- **Capability**: `BROWSER_AUTOMATION`
- **Tools**: `browser_control`
- **Model requirements**: text generation, tool calling
- **Max declared risk**: HIGH
- **Limitations**: uses the existing persistent Playwright session behind
  `browser_control` — does not and must not create a second browser
  controller.

## computer_agent — Computer Agent

- **Responsibility**: direct computer interaction — mouse/keyboard,
  OS settings, screen/camera capture, desktop automation.
- **Capability**: `COMPUTER_CONTROL`
- **Tools**: `computer_control`, `computer_settings`, `screen_process`,
  `desktop_control`
- **Model requirements**: text generation, tool calling, vision
- **Max declared risk**: **CRITICAL** (the `desktop_control` tool's `task`
  action runs LLM-generated code via `exec()`, not sandboxed — see the
  Phase 0 audit)
- **Limitations**: no additional safety layer beyond what each underlying
  tool already has; risk metadata is descriptive, not enforced.

## file_document_agent — File/Document Agent

- **Responsibility**: file management (list/create/delete/move/copy/rename)
  distinct from document intelligence (summarize/extract/convert uploaded
  files).
- **Capabilities**: `FILE_MANAGEMENT`, `DOCUMENT_INTELLIGENCE`
- **Tools**: `file_controller`, `file_processor`
- **Model requirements**: text generation, tool calling
- **Max declared risk**: HIGH
- **Limitations**: does not implement any new memory/project-context
  system — that's Phase 5.

## verification_agent — Verification Agent

- **Responsibility**: determining whether a completed task actually
  satisfies its goal (e.g. running tests/builds), rather than trusting a
  prior step's self-report.
- **Capability**: `VERIFICATION`
- **Tools**: `code_helper` (for `run`/`build` actions), `system_status`
- **Model requirements**: text generation, tool calling
- **Max declared risk**: HIGH
- **Limitations**: Phase 4's verification is tool-based only (run a
  command, check the result) — no sophisticated autonomous self-correction
  loop beyond the Orchestrator's normal bounded step-retry.

## Orchestrator

Not itself an `Agent` — the central coordinator that owns Task creation,
calls the Planner, selects agents deterministically by capability, executes
steps (with bounded retries and loop protection), and produces the final
structured `Task`. See `core/agent/orchestrator.py` and the architecture
doc for full detail.

## Planner

Not itself an `Agent` — converts a goal into a structured, validated plan
via the Model Gateway (`task_type="planner"`), with bounded corrective
retries on invalid output. See `core/agent/planner.py`.

## Entry point: run_agent_task tool

The bridge from Gemini Live's tool-calling into this whole layer — see
`core/agent/entrypoint.py` and the architecture doc's "Why opt-in, and how"
section. Registered into the same Tool Registry as the 21 Phase 3 tools;
Gemini decides when to call it based on its description, exactly like any
other tool.
