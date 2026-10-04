# Tool System Architecture

Phase 3 replaces `main.py`'s hardcoded 19-branch `if/elif` tool dispatcher
and hardcoded `TOOL_DECLARATIONS` list with a standardized Tool Registry /
Executor layer under `core/tools/`.

## Why

Before Phase 3, every tool Gemini could call was declared twice: once as a
hand-written Gemini function-declaration dict in `main.py`, and once as an
`if name == "...":` branch that called into `actions/*.py`. Adding a tool
meant touching both places and keeping them in sync by hand. There was also
no place to attach metadata (risk level, timeout, capabilities) that later
phases (permissions, missions, multi-agent orchestration) would need.

## The pieces

```
Agent / Gemini Live
        │
   Tool Registry        (core/tools/registry.py)   — the single source of truth
        │
   Tool Definition        (core/tools/base.py::Tool) — name, schema, metadata
        │
   Tool Executor           (core/tools/executor.py)  — validate, run, time, normalize
        │
   Existing Tool Implementation (actions/*.py — unmodified)
```

### Tool interface (`base.py`)

```python
class Tool(ABC):
    name: str
    description: str
    schema: ToolSchema
    metadata: ToolMetadata

    async def execute(self, args: dict, context: ToolContext) -> ToolResult: ...
    async def verify(self, result: ToolResult, context: ToolContext) -> VerificationResult | None: ...
    def gemini_declaration(self) -> dict: ...
```

Every concrete tool in `core/tools/definitions.py` implements this. Two
patterns are used:

1. **Standard action wrappers** (17 of 21 tools): `execute()` calls straight
   into the existing, unmodified `actions/*.py` function via
   `loop.run_in_executor` — no logic is duplicated, this file is glue.
2. **JARVIS-runtime-coupled tools** (`save_memory`, `screen_process`,
   `close_camera`, `shutdown_jarvis`): these replicate the exact
   special-case logic that used to live inline in `main.py`'s dispatcher
   (vision cooldown state, camera-stream UI control, silent function
   responses, process shutdown), reached via `context.extra["live"]` — see
   below.

### ToolContext (`base.py`)

```python
@dataclass
class ToolContext:
    request_id: str
    task_id: str | None = None
    user_id: str | None = None
    config: Any = None
    cancellation_token: CancellationToken
    logger: logging.Logger
    extra: dict[str, Any]
```

Most fields are optional/future-facing (task/user IDs don't mean anything
yet — no Mission system exists). `extra` is a deliberate, documented escape
hatch: `main.py` passes `{"ui": self.ui, "speak": self.speak, "live": self}`
so the handful of tools that need direct JARVIS runtime access (vision
cooldown state, the PyQt UI handle) can reach it without Phase 3 inventing
premature abstractions for state that a later session/mission system will
formalize properly. **Standard tools never touch `extra["live"]`** — only
`screen_process`, `shutdown_jarvis`, and (indirectly, for the UI handle)
most other tools use `extra["ui"]`/`extra["speak"]`.

### ToolSchema (`schemas.py`)

Provider-neutral parameter list. The canonical flow is:

```
ToolSchema  →  ToolSchema.to_gemini_declaration()  →  Gemini function declaration
```

never the reverse — nothing in the tool layer depends on Gemini's specific
JSON-schema dialect (`"STRING"`, `"OBJECT"`, uppercase type names) except
that one conversion method. `ToolSchema.validate(args)` does simple
required-field/type/enum checking (spec Part 19: "use the simplest reliable
validation mechanism" — not a full JSON-Schema validator).

### ToolMetadata (`metadata.py`)

```python
@dataclass(frozen=True)
class ToolMetadata:
    category: ToolCategory
    risk_level: RiskLevel                  # LOW | MEDIUM | HIGH | CRITICAL
    capabilities: tuple[Capability, ...]
    timeout_seconds: float | None
    supports_cancellation: bool
    requires_confirmation: bool             # not enforced yet
    supports_verification: bool
    supports_dry_run: bool
    permissions: tuple[str, ...]
    notes: str
```

Risk levels are seeded directly from the Phase 0 security audit's KEEP/
REFACTOR/REBUILD matrix — see `docs/tools.md` for the full table. **This is
metadata only.** No approval workflow, policy engine, or enforcement exists
yet — a `CRITICAL` tool executes exactly as before. Phase 6 will read this
metadata to build the actual permission/approval system.

### Tool Registry (`registry.py`)

`ToolRegistry.register(tool)` raises `ToolRegistrationError` on a duplicate
name. `get(name)`, `list()`, `list_names()`, `list_by_category()`,
`exists()`, `unregister()`. `generate_gemini_declarations()` is the new
canonical source for `main.py`'s `TOOL_DECLARATIONS` — it replaced the
hardcoded list entirely (`main.py` still exposes a `TOOL_DECLARATIONS`
module-level variable for compatibility, but it's now computed, not
hand-written).

`get_default_registry()` builds the registry once, lazily, calling
`definitions.register_all_tools()` — matching the spec's performance
requirement (Part 38: build once, don't rebuild per call).

### Tool Executor (`executor.py`)

```
find tool → validate input → (start audit event) → execute (with timeout)
    → normalize errors → measure duration → verification hook (if supported)
    → (completed/failed audit event) → return ToolResult
```

- **Validation failures** and **unknown tool names** return a structured
  `ToolResult.fail(...)` rather than raising — matches spec Part 19.
- **Timeouts**: each tool declares `metadata.timeout_seconds`; the executor
  wraps `execute()` in `asyncio.wait_for()`. Not every tool's underlying OS
  automation is actually safe to interrupt mid-operation (spec Part 20) —
  see the per-tool notes in `docs/tools.md` for which are
  SUPPORTED/LIMITED/NOT SAFE.
- **Cancellation**: `CancellationToken` is a cooperative flag
  (`token.is_cancelled`), not a forced interrupt — nothing here yanks
  control away from a running `pyautogui` call, which could leave the OS in
  a half-completed state.
- **Verification hook**: `tool.verify(result, context)` is called only if
  `metadata.supports_verification` is `True`. Currently no production tool
  opts in — the hook exists and is invoked correctly (tested), ready for a
  future phase to use.
- **Audit hook**: emits `ToolEvent(type="started"|"completed"|"failed", ...)`
  through Phase 1's `logging` — no durable audit database yet (Phase 6).

### Error taxonomy (`errors.py`)

`ToolNotFoundError`, `ToolValidationError`, `ToolExecutionError`,
`ToolTimeoutError`, `ToolCancelledError`, `ToolVerificationError`,
`ToolRegistrationError`. The executor logs full exception detail
(`logger.exception(...)`) for developers but returns a concise
`ToolResult.error`/`message` to the model — no raw traceback is sent back
through the Gemini function-response channel.

## Gemini integration

```
Tool Registry
      ↓ generate_gemini_declarations()
Gemini function declarations  (sent once, at session start, in main.py)
      ↓
Gemini Live session  (unchanged — see docs/architecture/model-gateway.md)
      ↓ FunctionCall
main.py::_execute_tool(fc)
      ↓
ToolContext(extra={"ui":..., "speak":..., "live": self})
      ↓
ToolExecutor.execute(fc.name, args, context)
      ↓
ToolResult
      ↓ .as_model_text()
types.FunctionResponse(id=fc.id, name=fc.name, response={"result": ..., "silent": ...})
      ↓
Gemini
```

`main.py`'s realtime audio session lifecycle (`_send_realtime`,
`_listen_audio`, `_receive_audio`, `_play_audio`, interrupt handling) is
**completely untouched** — only `_execute_tool`'s body and the module-level
`TOOL_DECLARATIONS` assignment changed.

## Sync/async handling

Most existing `actions/*.py` functions are synchronous. Every standard tool
wrapper runs its underlying function via
`loop.run_in_executor(None, lambda: fn(...))` inside an `async def
execute()` — identical to what `main.py`'s old dispatcher did with
`loop.run_in_executor`. The Executor itself is fully `async` and works
uniformly whether a tool's `execute()` awaits a `run_in_executor` call
(the common case) or does genuinely async work directly (none of the
current 21 do, but the interface supports it — no new concurrency framework
was introduced, per spec Part 28).

## Special handling preserved

- **Browser control**: `browser_control.py`'s persistent background
  Playwright session/event loop is untouched — `BrowserControlTool` just
  calls the existing `browser_control()` function once per tool call, same
  as before.
- **Gemini Live / screen processor**: `GeminiLiveAdapter` (Phase 2) is
  unaffected; `ScreenProcessTool` only replicates the *dispatch* logic
  (cooldown check, camera-stream toggling, setting `_pending_vision` on the
  `live` object) — it does not touch the realtime session itself.
- **Developer agent**: `DevAgentTool`/`CodeHelperTool` call
  `dev_agent()`/`code_helper()` unmodified; both remain `CRITICAL`/`HIGH`
  risk per the Phase 0 audit, with an explicit `notes` field documenting why.
- **File processor**: `FileProcessorTool` preserves the exact
  default-file-path injection behavior (`ui.current_file` fallback) and
  does not touch `file_processor()`'s internal vision/image handling at all.
- **Desktop generated-code execution**: `DesktopControlTool` is classified
  `CRITICAL` with an explicit `notes` field pointing at the Phase 0 audit;
  no sandboxing was attempted (that's Phase 6, per the spec).

## What Phase 3 does NOT do

- No multi-agent orchestration, Planner Agent, or Agent Registry (Phase 4).
- No Mission system.
- No policy engine, approval workflow, or sandbox rebuild (Phase 6) — risk
  metadata exists and is queryable, but nothing enforces it yet.
- No plugin marketplace.
