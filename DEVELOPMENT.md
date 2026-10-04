# Development Guide

## Project structure

```
MARK XLVIII/
├── main.py                  # Gemini Live session + tool dispatcher (unchanged in Phase 1)
├── ui.py                    # PyQt6 HUD
├── actions/                 # one module per tool (20 modules)
├── core/
│   ├── config/               # Phase 1: centralized config & secrets
│   │   ├── service.py         # ConfigService — the single config entry point
│   │   ├── secrets.py         # SecretStore — keyring, with local-file fallback
│   │   ├── certs.py           # runtime self-signed TLS cert generation
│   │   └── models.py          # typed views (PathsConfig, DashboardConfig, EngineConfig)
│   ├── logging_setup.py      # Phase 1: stdlib logging + secret redaction
│   ├── installer.py          # first-run convenience dependency installer
│   ├── llm_client.py         # Ollama / OpenAI-compatible client (not yet wired into main.py)
│   ├── stt.py / tts.py       # speech engine selection
│   └── prompt.txt            # Gemini Live system prompt
├── dashboard/
│   └── server.py             # FastAPI remote-control web server
├── memory/
│   ├── memory_manager.py     # user-facts memory store
│   └── config_manager.py     # DEPRECATED shim -> core.config (kept for compatibility)
├── tests/                    # Phase 1 foundation tests
├── requirements.txt          # dependency manifest (source of truth)
├── JARVIS_PHASE0_AUDIT.md    # full repository audit + phased roadmap
└── README.md / DEVELOPMENT.md / SECURITY.md
```

## Configuration service

**Do not** read `config/api_keys.json`, `config/app_config.json`, or
`config/secrets.json` directly anywhere in the codebase. Use:

```python
from core.config import get_config_service

config = get_config_service()

# Secrets
api_key = config.get_gemini_api_key()          # raises RuntimeError if unset
config.set_secret("gemini_api_key", "AIza...")

# Non-secret settings
os_name = config.get("os_system", "windows")
config.set("dashboard_port", 8000)

# Typed views
paths = config.paths()
dash  = config.dashboard()
eng   = config.engines()
```

`ConfigService` is a process-wide singleton (`ConfigService()` always returns
the same instance). It is safe to call `get_config_service()` from any
module, at any time, including inside a function body (avoids import-order
issues — several `actions/*.py` modules do this deliberately).

### Adding a new secret

Add the key name to `_SECRET_KEYS` in `core/config/service.py`. That's the
only place that distinguishes "goes in `app_config.json`" from "goes in the
`SecretStore`".

### Legacy migration

`core/config/service.py`'s `ConfigService.reload()` checks for
`config/api_keys.json` on every load. If present, it copies:
- the `gemini_api_key` value into the `SecretStore` (keychain or local
  fallback file), and
- every other key into `config/app_config.json`

...but only for keys not already present in the new stores (idempotent,
won't clobber a value you've since changed through the app). **The legacy
file is never deleted or written to** by this process — if migration fails
to parse it, `ConfigService.migration_note` reports why, and the app
continues with whatever the new stores already have.

## Secret storage backend

`core/config/secrets.py`'s `SecretStore` tries, in order:
1. OS keychain via the `keyring` package (Windows Credential Locker / macOS
   Keychain / Linux Secret Service).
2. A local JSON file at `config/secrets.json`, created with owner-only
   permissions where the OS supports it (POSIX `chmod 600`; a no-op on
   Windows, which uses ACLs instead).

Check which backend is active:

```python
get_config_service().secret_backend()   # "os-keychain (keyring)" or "local-file-fallback"
```

Both paths keep secrets out of the tracked source tree — the difference is
encryption-at-rest strength, not git-safety.

## TLS certificates (dashboard)

`core/config/certs.py`'s `ensure_self_signed_cert()` generates a fresh
self-signed cert/key pair into `config/certs/` the first time the dashboard
starts and none exists. Nothing under `config/certs/` is tracked by git.
Deleting that directory and restarting the app regenerates a fresh pair.

## Logging

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Dashboard listening on %s", url)
logger.warning("Camera index %d gave no usable frame", idx)
logger.error("Tool execution failed: %s", exc)
```

Call `core.logging_setup.configure_logging()` once, at process startup
(already wired into `main.py`). It sets up:
- a console handler,
- a rotating file handler at `logs/jarvis.log` (2 MB × 3 backups),
- a `SensitiveDataFilter` on both handlers that redacts known secret values
  and secret-shaped substrings (API keys, bearer tokens) from every record.

If you obtain a secret value directly (rare — most code goes through
`ConfigService`), call `core.logging_setup.register_secret(value)` so it's
scrubbed from logs even if it ends up in a message by mistake.

`configure_logging()` is idempotent — safe to call more than once.

## Testing

```bash
pip install pytest
python -m pytest tests/ -v
```

Phase 1 tests cover the new foundation only (config service, secret store,
logging, cert generation, a startup-sequence characterization test). They do
**not** require a real Gemini API key, network access, PyQt6, or an audio
device — external calls and heavier dependencies are avoided or isolated via
fixtures in `tests/conftest.py`, which resets the `ConfigService` singleton
and redirects all config/secret paths into a temp directory per test.

There is no test coverage yet for `actions/*.py` tool behavior, the Gemini
Live session itself, or the dashboard's WebSocket/auth flows — that is
explicitly out of scope for Phase 1 (see the Phase 0 audit's Part 21/24 for
the planned full testing strategy).

## Model Gateway (Phase 2)

See `docs/architecture/model-gateway.md` for the full architecture and
`docs/providers.md` for current provider support status. Quick reference:

```python
from core.llm.gateway import generate_text
reply = generate_text("Summarize this...", task_type="coding")
```

### Adding a new provider

1. Create `core/llm/providers/your_provider.py`, subclassing
   `core.llm.providers.base.Provider`. Implement `list_models()`,
   `health_check()`, `generate(request, model_id)`, and optionally
   `stream(request, model_id)`.
2. Translate every provider-specific exception into one of
   `core.llm.errors`' types at the point you catch it — the Gateway only
   understands that hierarchy.
3. Register a factory in `core/llm/registry.py::get_default_registry()`:
   `registry.register("your_provider", lambda: _build_your_provider(config))`.
   Keep construction lazy — don't touch the network in the factory itself.
4. Add it to the routing tables in `core/llm/router.py` if it should be a
   default candidate for any `task_type`.
5. Write tests under `tests/llm/` following `test_ollama_provider.py` or
   `test_openai_compatible_provider.py` as a template — mock `requests`
   (or the SDK, see `test_gemini_provider.py`'s `_install_fake_genai`
   pattern) rather than hitting a real endpoint.
6. Update `docs/providers.md`'s status table — SUPPORTED only once
   `generate()` actually works end-to-end with mocked tests passing.

### Adding a new model to an existing provider

Add an entry to that provider's `list_models()` (most adapters have a
static `_MODELS` list, e.g. `providers/gemini.py`) with accurate
`ModelCapabilities` — don't set `tool_calling=True` etc. unless you've
verified it.

### Writing provider tests / using mocked providers

- For adapters that call an HTTP API (Ollama, OpenAI-compatible): mock
  `requests.get`/`requests.post` via `unittest.mock.patch`, as in
  `tests/llm/test_ollama_provider.py`.
- For the Gemini SDK adapter: install a fake `google.genai` module into
  `sys.modules` before importing, as in
  `tests/llm/test_gemini_provider.py::_install_fake_genai` — this avoids
  needing the real `google-genai` package installed for the test suite.
- For Router/Gateway tests that don't care about a specific provider's
  wire format: use `tests/llm/conftest.py`'s `FakeProvider`, a fully
  in-memory `Provider` implementation.
- **Never** require a real API key or network access for anything under
  `tests/llm/` — mark any genuine smoke test against a live provider
  clearly separately (none exist yet in this repo).

## Tool Registry (Phase 3)

See `docs/architecture/tool-system.md` for the full architecture and
`docs/tools.md` for the current tool inventory (names, risk levels,
categories). Quick reference:

```python
from core.tools import get_default_registry, ToolExecutor, ToolContext

registry = get_default_registry()
executor = ToolExecutor(registry)
context = ToolContext(extra={"ui": ui, "speak": speak})
result = await executor.execute("open_app", {"app_name": "Chrome"}, context)
```

### Adding a new tool

1. Add your implementation to an existing or new `actions/*.py` module —
   this hasn't changed. Keep it a plain, testable function.
2. In `core/tools/definitions.py`, add a `Tool` subclass:
   ```python
   class MyTool(Tool):
       name = "my_tool"
       description = "One or two sentences — this is what the model reads
                       to decide when to call it. Be specific."
       schema = ToolSchema((
           ParamSchema("some_arg", "string", "What this arg means", required=True),
       ))
       metadata = ToolMetadata(category=ToolCategory.SYSTEM, risk_level=RiskLevel.LOW,
                                timeout_seconds=20)

       async def execute(self, args: dict, context: ToolContext) -> ToolResult:
           from actions.my_module import my_function
           ui = context.extra.get("ui")
           r = await _run_sync(lambda: my_function(parameters=args, player=ui))
           return ToolResult.ok(self.name, data=r or "Done.")
   ```
3. Add it to the `tools = [...]` list in `register_all_tools()`.
4. Set `risk_level` honestly — see the Phase 0 audit's security assessment
   and `docs/tools.md`'s existing classifications for calibration. CRITICAL
   is for unsandboxed code/command execution; HIGH for destructive
   file/computer/browser control; MEDIUM for reversible OS/app actions; LOW
   for read-only/informational calls.
5. If your tool needs direct JARVIS runtime state (the UI handle, the
   `speak()` callback, in-session state) beyond what a normal
   `actions/*.py` function needs, read it from `context.extra` — don't add
   new global state. See `ScreenProcessTool`/`ShutdownJarvisTool` for the
   pattern.
6. Write tests in `tests/tools/test_production_tools.py` (or a new file):
   at minimum a registration/metadata check and a mocked-execution test.
   Mock the underlying `actions/*.py` function with
   `unittest.mock.patch("actions.my_module.my_function", ...)` — never let
   tests actually move the mouse, delete files, open a browser, etc.
7. Add a row to `docs/tools.md`'s table.

### How Gemini function schemas are generated

You do **not** write a Gemini-specific declaration by hand. `ToolSchema`
is provider-neutral; `Tool.gemini_declaration()` (via
`ToolSchema.to_gemini_declaration()`) converts it automatically. `main.py`
calls `registry.generate_gemini_declarations()` once at startup — there is
no second place to keep in sync.

### Testing a new tool

```python
import pytest
from unittest.mock import MagicMock, patch
from core.tools.base import ToolContext
from core.tools.registry import get_default_registry

@pytest.mark.asyncio
async def test_my_tool():
    with patch("actions.my_module.my_function", return_value="ok"):
        tool = get_default_registry().get("my_tool")
        result = await tool.execute({"some_arg": "x"}, ToolContext(extra={"ui": MagicMock()}))
    assert result.success is True
```

Run with `python -m pytest tests/tools/ -v` (requires `pytest-asyncio`;
`pytest.ini` at the repo root already sets `asyncio_mode = auto`).

### Setting risk metadata

Risk metadata (`ToolMetadata.risk_level`, `.capabilities`, `.notes`) is
**descriptive only** in Phase 3 — nothing enforces it yet (no approval
workflow, no policy engine; that's Phase 6). Set it accurately anyway:
future phases will read it, and `docs/tools.md`'s table is generated by
hand from these values, so an inaccurate risk level actively misleads
anyone auditing the tool surface later.

## Multi-Agent Runtime (Phase 4)

See `docs/architecture/multi-agent-runtime.md` for the full architecture
and `docs/agents.md` for the current agent inventory. Quick reference:

```python
from core.agent import get_default_orchestrator

task = await get_default_orchestrator().run_task(
    "research the best database for this project and recommend one"
)
print(task.summary())
for step in task.steps:
    print(step.step_id, step.status, step.assigned_agent)
```

This is opt-in — it does not run for ordinary tool calls. The realtime
voice path (`main.py`) reaches it only through the `run_agent_task` tool,
which Gemini calls when it judges a request to be genuinely multi-step.

### Adding a new agent

1. Decide it's actually justified: does it have a distinct capability
   boundary, meaningful tool access, and (ideally) a reason to reason
   differently from the existing six? If an existing agent's tool set
   already covers it, extend that agent's `tool_names` instead of adding a
   new one (spec Part 49 — avoid "agent theater").
2. In `core/agent/agents.py`, subclass `ToolUsingAgent` (not `Agent`
   directly, unless you need custom `handle()` logic beyond "pick a tool
   and run it" — see `FailingAgent` in `tests/agent/conftest.py` for what a
   from-scratch `Agent` looks like):
   ```python
   class MyAgent(ToolUsingAgent):
       agent_id = "my_agent"
       name = "My Agent"
       description = "One or two sentences describing its job."
       metadata = AgentMetadata(
           capabilities=(AgentCapability.RESEARCH,),   # add a new AgentCapability in base.py if genuinely needed
           tool_names=("web_search",),                  # ONLY tools this agent may call
           model_requirements=ModelCapabilities(text_generation=True, tool_calling=True),
           max_declared_risk=RiskLevel.LOW,              # match your riskiest declared tool — see docs/tools.md
       )
   ```
3. Add it to `register_all_agents()`'s tuple.
4. Add a row to `docs/agents.md`.
5. Write tests: at minimum, a registration/metadata check
   (`tests/agent/test_agent_registry.py`-style) and a mocked
   Orchestrator-level test showing the Planner's `required_capabilities`
   routes a step to your agent (`tests/agent/test_agent_selection.py`-style).
   Use `tests/agent/conftest.py`'s `make_fake_gateway()` to avoid any real
   model/network call.

### How an agent accesses tools

Only through `context.tool_registry`/`context.tool_executor` — never
`import actions.something` directly (enforced by
`tests/agent/test_architecture.py`'s static check). `ToolUsingAgent`
already does this correctly; if you're writing a custom `Agent.handle()`,
call `context.tool_executor.execute(name, args, context.make_tool_context())`.

### How an agent accesses the Model Gateway

Only through `context.model_gateway.generate(request, task_type=...)` —
never a provider SDK directly (also statically checked). See
`ToolUsingAgent._decide_tool_call()` for the pattern: build a
`core.llm.types.ModelRequest`, call `.generate()`, parse `.content`.

### How to test agents

```python
import pytest
from core.agent.task import TaskStep
from tests.agent.conftest import make_context, make_fake_gateway  # or copy the pattern locally

@pytest.mark.asyncio
async def test_my_agent():
    gateway, provider = make_fake_gateway('{"tool": "web_search", "arguments": {"query": "x"}}')
    agent = MyAgent()
    step = TaskStep(step_id="s1", description="look something up")
    context = make_context(tool_registry, tool_executor, model_gateway=gateway)
    result = await agent.handle(step, context)
    assert result.success is True
```

Run with `python -m pytest tests/agent/ -v`. Never call a real provider or
move a real mouse/browser/file in an agent test — mock at the Gateway
(`make_fake_gateway`) or Tool (`unittest.mock.patch("actions.x.y", ...)`)
boundary, following `tests/tools/test_production_tools.py`'s pattern for
the latter.

## Memory (Phase 5)

See `docs/architecture/memory-system.md` for the full architecture and
`docs/memory.md` for what belongs in each memory layer. Quick reference:

```python
from core.memory import get_default_memory_service, MemoryType, Source, RetrievalQuery

memory = get_default_memory_service()
memory.remember("User prefers dark mode", MemoryType.PREFERENCE, source=Source.USER)
results = memory.retrieve(RetrievalQuery(query="dark mode", memory_types=(MemoryType.PREFERENCE,)))
```

Agents access memory via `context.memory` (an `AgentContext` field) or the
convenience `context.retrieve_memory(query, ...)` wrapper — never by
importing `core.memory.stores` or `memory.memory_manager` directly (both
are statically checked, see `tests/memory/test_architecture.py`).

### How to create memory records

Use the typed sub-layer that matches what you're storing (see
`docs/memory.md`'s decision guide) — `memory.working`, `.preferences`,
`.episodic`, `.semantic`, `.projects` — rather than the generic
`MemoryService.remember()` unless you genuinely have a one-off record that
doesn't fit a specific layer's convenience API:

```python
memory.episodic.record_event("Task completed: fixed the build",
                              result="tests passing", importance=0.7)
memory.projects.set_fact(project_id, "tech_stack", "Python + FastAPI")
memory.semantic.remember_fact("Python is dynamically typed", concept="python")
```

### How agents retrieve memory

```python
async def handle(self, step, context):
    relevant = context.retrieve_memory(step.description, limit=5)
    # relevant: list[RetrievalResult], each with .record and .relevance
    ...
```

This never raises — a memory outage returns `[]`, so retrieval failures
degrade gracefully rather than blocking the agent's actual work (spec Part
40). `Orchestrator` already retrieves relevant memory before calling the
Planner and records a task-outcome episodic event automatically — most
agents don't need to touch memory explicitly at all unless they have a
project/domain-specific reason to (see `DeveloperAgent` for an example).

### How to create a new memory store

Subclass `core.memory.stores.base.MemoryStore`, implementing all abstract
methods (`save`, `get`, `update`, `delete`, `delete_by_namespace`,
`delete_by_project`, `search`, `all`, `purge_expired`). Wire it into
`MemoryService`'s constructor (or `get_default_memory_service()` if it
should become the new default) — nothing above the `MemoryStore` interface
needs to change. Write tests following `tests/memory/test_stores.py`'s
parametrized pattern (it tests `JsonMemoryStore` and `SqliteMemoryStore`
against the same test cases, since both must satisfy the same interface).

### How migration works

`core.memory.migration.migrate_legacy_json(legacy_path, preference_memory)`
is idempotent and additive — safe to call repeatedly, never overwrites a
value the user has since changed, never deletes the original file. It runs
automatically inside `MemoryService.__init__()` when a `legacy_json_path`
is supplied (which `get_default_memory_service()` always does, pointing at
`memory/long_term.json`). Check `service.migration_report.summary()` after
construction if you need to inspect what happened.

### How to test memory behavior

Use `tests/memory/conftest.py`'s fixtures (`preference_store`,
`durable_store`, `memory_service`, `memory_service_disabled`) — all
`tmp_path`-backed, never touching the real `memory/` directory. **Do not**
call `core.memory.get_default_memory_service()` in a test without
monkeypatching it to an isolated instance first — it writes to the real
`memory/preferences.json` / `memory/memory.db` under the repo, which you do
not want polluted by a test run (see
`tests/memory/test_regression.py::test_memory_manager_shim_backward_compatible_api`
for the monkeypatch pattern).

## Policy & Sandbox (Phase 6)

See `docs/architecture/security-and-policy.md`, `docs/security-model.md`,
and `docs/sandbox.md`. Quick reference:

```python
from core.policy import get_default_policy_engine, PolicyContext, PolicyDecision
from core.tools.metadata import RiskLevel

engine = get_default_policy_engine()
result = engine.evaluate(PolicyContext(tool_name="file_controller", risk_level=RiskLevel.HIGH))
print(result.decision, result.reason)
```

### Setting a tool's risk correctly

`ToolMetadata.risk_level` is no longer just descriptive — it now
determines real behavior (ALLOW/APPROVAL_REQUIRED/DENY). If your tool
executes model-generated code or shell commands, also set
`requires_sandbox=True` so the PolicyEngine refuses to run it when no
sandbox is available, rather than silently falling back to an unsandboxed
host run.

### Testing code that goes through the Policy Engine

**All Phase 1-5 tests, and any test that doesn't specifically test policy
behavior, run under a permissive "allow everything" `PolicyEngine`** —
this is set up by an autouse fixture in the root `tests/conftest.py`
(`_reset_policy_singletons`). You don't need to do anything special for a
LOW-risk tool test to keep working. If your tool is HIGH/CRITICAL risk and
you're writing a test that calls it through the full `ToolExecutor` (not
directly via `tool.execute()`), it will run under that permissive default
unless you explicitly construct your own `PolicyEngine`/`PolicyConfig`
(see `tests/policy/test_executor_integration.py` for the pattern) —
otherwise it will just execute, same as before Phase 6.

Tests that specifically exercise policy/approval behavior build their own
`PolicyEngine`/`ApprovalManager` and pass them explicitly to `ToolExecutor`
— see `tests/policy/` for the full pattern, including how to simulate
approve/deny/timeout without actually waiting the full timeout duration
(pass a short `approval_timeout_seconds` in the test's `PolicyConfig`).

### Adding a sandboxed execution path

Use `core.sandbox.get_default_sandbox_manager()`:

```python
from core.sandbox import get_default_sandbox_manager, ResourceLimits
from core.tools.metadata import RiskLevel

manager = get_default_sandbox_manager()
result = manager.execute_command(["python3", "-c", "print('hi')"],
                                  risk_level=RiskLevel.HIGH,
                                  limits=ResourceLimits(timeout_seconds=30))
print(result.stdout, result.exit_code)
```

Never call `subprocess`/`exec`/`eval` directly on model-generated content
— route it through `SandboxManager` instead, and mark the owning tool
`requires_sandbox=True`. If your use case genuinely cannot be
containerized (e.g. it needs host GUI access, like
`desktop_control`), don't fake sandboxing — document why (see
`docs/sandbox.md`'s "what is NOT sandboxed" section for the template) and
rely on mandatory approval as the real safeguard instead.

## Code style / conventions carried over from before Phase 1

- Action modules are synchronous; `main.py` calls them via
  `loop.run_in_executor`.
- Each `actions/*.py` module is self-contained and may re-declare small
  helpers (`_get_base_dir()`, etc.) rather than sharing a common util module
  — this hasn't been consolidated in Phase 1 to keep the change surface
  small; it's flagged in the Phase 0 audit as a Phase 3+ cleanup candidate.
