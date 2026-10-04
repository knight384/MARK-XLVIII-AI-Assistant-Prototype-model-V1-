# Multi-Agent Runtime Architecture

Phase 4 adds `core/agent/` — an opt-in orchestration layer on top of the
Phase 2 Model Gateway and Phase 3 Tool Registry/Executor, for complex,
multi-step goals. It does **not** replace the existing single-agent Gemini
Live voice path, which remains the default for everything else.

## Why "opt-in," and how

Simple voice commands ("open Chrome," "what's the weather") must stay fast.
Rather than teach `main.py`'s realtime audio loop to classify every
utterance as simple-or-complex, Phase 4 adds exactly one new tool —
`run_agent_task` — to the same Tool Registry the other 21 tools live in.
Gemini itself decides when to call it, using the same mechanism it already
uses to decide between `open_app` and `web_search`: the tool's description.
`run_agent_task`'s description explicitly says "use this ONLY for complex,
multi-step goals... do NOT use this for a single simple action."

This means:
- **Zero changes** to `main.py`'s realtime send/receive/audio-loop code.
- **Zero added latency** for simple requests — no new model call, no new
  code path runs unless this specific tool is chosen.
- The Orchestrator still only ever executes real actions through the
  canonical `ToolExecutor` — `Tool (run_agent_task) → Orchestrator → Agents
  → Tool Registry → Tool Executor → Tool`, never a second execution path.

```
Gemini Live
    │
    ├── Simple request → any of the 21 Phase 3 tools → Tool Executor
    │
    └── Complex request → run_agent_task tool
                              │
                          Orchestrator
                              │
                           Planner
                              │
                    Structured Execution Plan
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         DeveloperAgent  ResearchAgent  ...(4 more)
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                        Tool Registry
                              │
                        Tool Executor   (same instance as the simple path)
                              │
                       Existing Tools
```

A deterministic, non-LLM complexity heuristic (`core/agent/complexity.py::
is_complex_request()`) is also provided — tested, documented, but **not**
wired to gate anything in this phase (spec Part 32 prefers deterministic
routing "first," but the tool-description approach above achieves the same
opt-in guarantee with less risk to the realtime path; the heuristic is
available for a future revision that wants explicit routing instead).

## The pieces

### Task / TaskStep (`task.py`)

In-memory only — no database (spec Part 37/7: "In-memory task state is
acceptable for Phase 4"). `Task` owns `status` (CREATED → PLANNING →
RUNNING → COMPLETED/FAILED/CANCELLED), a list of `TaskStep`, and a list of
`Observation`s. Each `TaskStep` has a simple dependency gate
(`is_ready()`) — not a full DAG scheduler; sequential execution with
skip-on-failed-dependency is enough for Phase 4's scope.

### AgentResult / Observation (`result.py`)

Structured, not free-form text (spec Part 6/22 — "do not force agents to
exchange free-form natural-language conversations"). `AgentResult` carries
`success`, `summary`, `tool_results` (actual Phase 3 `ToolResult`s),
`observations`, and `errors`. `Observation` has a `source` (`tool` /
`agent` / `system` / `verification` / `model`), letting the Orchestrator
build a structured trace instead of parsing prose.

### AgentContext (`context.py`)

Distinct from Phase 3's `ToolContext`. Carries the `Task`, the Model
Gateway, the Tool Registry/Executor, a `CancellationToken` (Phase 3's,
reused per spec Part 27), and a `shared` scratch dict for one task's run.
`AgentContext.make_tool_context()` is the one place that builds a
`ToolContext` from it, so every agent constructs tool calls consistently.
No raw provider SDK client is ever exposed here.

### Agent / ToolUsingAgent (`base.py`)

```python
class Agent(ABC):
    agent_id: str
    name: str
    description: str
    metadata: AgentMetadata
    async def handle(self, step: TaskStep, context: AgentContext) -> AgentResult: ...
```

`AgentMetadata` declares `capabilities` (an `AgentCapability` enum:
`CODING`, `RESEARCH`, `BROWSER_AUTOMATION`, `COMPUTER_CONTROL`,
`FILE_MANAGEMENT`, `DOCUMENT_INTELLIGENCE`, `VERIFICATION`),
`tool_names` (the *only* tools that agent may call), `model_requirements`
(reuses Phase 2's `ModelCapabilities`), and `max_declared_risk` (reuses
Phase 3's `RiskLevel` — **metadata only**, not enforced; Phase 6 will
enforce it).

`ToolUsingAgent` is a shared base implementing the common "pick one of my
declared tools and run it through the Tool Executor" pattern, so the six
specialized agents don't each reimplement it (spec Part 49: avoid "agent
theater"). Two paths:
1. **Explicit routing** — if the step already has `tool_name`/`tool_args`
   (from the Planner's structured output, or set directly by a caller),
   use them as-is.
2. **Model-assisted routing** — otherwise, ask the Model Gateway (never a
   provider SDK — spec Part 35) to choose from the agent's declared tools
   and produce JSON arguments.

Either path ends the same way: `context.tool_executor.execute(tool_name,
args, tool_context)` — the identical Phase 3 executor every other tool call
in the app uses.

### Agent Registry (`registry.py`)

Mirrors Phase 3's `ToolRegistry`: register/unregister/get/exists/list,
duplicate-ID rejection, plus `find_by_capability()` for deterministic agent
selection (spec Part 13: "Do not use an LLM to decide agent selection if a
deterministic capability match is sufficient").

### Planner (`planner.py`)

Converts a goal string into a validated `list[TaskStep]`, via
`ModelGateway.generate(request, task_type="planner")` — never a provider
SDK directly (spec Part 10). Requests JSON-only structured output; on
malformed/invalid output, retries with a corrective prompt, bounded by
`max_attempts` (default 2) — never an unbounded loop (spec Part 11).
Validation checks: non-empty `steps`, each step has a `description`, has
non-empty `required_capabilities` drawn only from the known
`AgentCapability` values, no duplicate step IDs, and every `dependencies`
reference points at a real step ID in the same plan.

### Orchestrator (`orchestrator.py`)

The central coordinator (spec Part 12/23 — exactly one, agents never spawn
children or talk to each other directly). `run_task(goal)`:

1. Create `Task`, check cancellation.
2. `Planner.plan(goal)` — on `InvalidPlanError`, mark the task `FAILED`
   and return (never raises out of `run_task` for ordinary planning
   failures — spec Part 26: failures must be visible in the result, not
   hidden behind an exception).
3. Reject plans exceeding `max_execution_steps` (loop protection).
4. Execute steps in dependency order (a simple readiness loop, bounded by
   `max_passes = len(steps) + 2` to prevent an unsatisfiable-dependency
   spin — not a full scheduler).
5. For each ready step: deterministic agent selection
   (`_select_agent()` — preferred_agent first, then first capability
   match), build an `AgentContext`, call `agent.handle()` with up to
   `max_step_retries` attempts on failure.
6. A step whose dependency failed is marked `SKIPPED`, not retried.
7. Cancellation is checked before every step; already-completed steps stay
   completed, remaining ones become `CANCELLED`.
8. `max_delegations` caps the total number of agent invocations
   independent of `max_execution_steps` (spec Part 24: multiple distinct
   loop-protection knobs).
9. Final `task.status` is `COMPLETED` only if every step succeeded —
   otherwise `FAILED`, with per-step status/error still visible for partial
   completion reporting (spec Part 26).

### Initial specialized agents (`agents.py`)

Six agents, each with a genuinely distinct tool set (tested —
`test_no_agent_theater_each_agent_has_distinct_tool_set`):

| Agent | Capability | Tools | Max declared risk |
|---|---|---|---|
| DeveloperAgent | CODING | `dev_agent`, `code_helper` | CRITICAL |
| ResearchAgent | RESEARCH | `web_search`, `weather_report`, `flight_finder` | LOW |
| BrowserAgent | BROWSER_AUTOMATION | `browser_control` | HIGH |
| ComputerAgent | COMPUTER_CONTROL | `computer_control`, `computer_settings`, `screen_process`, `desktop_control` | CRITICAL |
| FileDocumentAgent | FILE_MANAGEMENT, DOCUMENT_INTELLIGENCE | `file_controller`, `file_processor` | HIGH |
| VerificationAgent | VERIFICATION | `code_helper`, `system_status` | HIGH |

See `docs/agents.md` for the full per-agent writeup.

### Developer Agent migration note (spec Part 15/47)

`actions/dev_agent.py`'s plan→write→run→classify→fix loop was **not**
rewritten or duplicated. `DeveloperAgent` is a thin orchestration-layer
wrapper: it calls the existing `dev_agent`/`code_helper` Phase 3 tools
through `ToolUsingAgent`'s standard path, exactly like every other agent
calls its tools. The valuable internal logic stays exactly where it was.

## Cancellation

Reuses Phase 3's `CancellationToken` (spec Part 27) — a cooperative flag,
not a forced interrupt (matching Phase 3's own stance on not faking
cancellation of OS automation that can't safely be interrupted
mid-operation). The Orchestrator checks it before every step; a cancelled
task stops scheduling new steps and marks remaining ones `CANCELLED`
rather than silently dropping them.

## Loop protection (spec Part 24)

Four independent bounds, all constructor-configurable on `Orchestrator`:
- `Planner.max_attempts` (default 2) — bounded planning retries.
- `max_step_retries` (default 2) — bounded per-step agent retries.
- `max_execution_steps` (default 20) — rejects an oversized plan outright.
- `max_delegations` (default 20) — caps total agent invocations
  independent of plan size (protects against the scheduler's readiness
  loop re-visiting steps in ways `max_execution_steps` alone wouldn't
  catch).

## What Phase 4 does NOT do

- No persistent Mission database (Phase 9) — `Task` is in-memory, owned by
  one `Orchestrator.run_task()` call.
- No policy engine / approval enforcement (Phase 6) — `max_declared_risk`
  is metadata, read but not enforced.
- No distributed/multi-process agent deployment (Phase 7).
- No message broker / distributed event bus — agent "communication" is
  structured Python objects passed through the Orchestrator, never
  free-form agent-to-agent chat (spec Part 22).
- No unlimited recursive agent delegation (spec Part 23) — the hierarchy is
  strictly `Orchestrator → Agent`, never `Agent → Agent`.
