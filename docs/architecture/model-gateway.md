# Model Gateway Architecture

Phase 2 introduces `core/llm/` — a provider-agnostic layer between JARVIS's
agent/tool code and individual AI vendors. This document explains the
pieces and how they fit together.

## Why

Before Phase 2, `main.py`, `actions/dev_agent.py`, `actions/desktop.py`,
`actions/code_helper.py`, and 7 other action modules each independently
constructed a `google.genai.Client` and called `generate_content()`. Adding
a new provider meant editing every one of those files. `core/llm_client.py`
(a fully-working Ollama/OpenAI-compatible client) existed but was never
actually wired into the running application.

The Model Gateway fixes both problems: one abstraction that the rest of
JARVIS depends on, and Ollama/OpenAI-compatible providers that are now
actually selectable.

## The pieces

```
Application / Agent
        │
   ModelRouter        (core/llm/router.py)      — picks provider+model
        │
   ModelGateway        (core/llm/gateway.py)     — retry, fallback, calls the provider
        │
   ProviderRegistry     (core/llm/registry.py)   — lazy construction, lookup, health checks
        │
   Provider adapter      (core/llm/providers/*.py)
        │
   Actual SDK / HTTP call
```

### Provider abstraction (`providers/base.py`)

Every adapter implements `Provider`: `list_models()`, `health_check()`,
`generate(request, model_id)`, and optionally `stream(request, model_id)`.
The Gateway/Router never call a vendor SDK directly — they only ever call
through this interface. `is_configured()` is a cheap, local, no-network
check (e.g. "is an API key set"), separate from `health_check()`, which may
do a real reachability check.

### Model abstraction (`providers/base.py::ModelInfo`)

Each model a provider exposes carries `model_id`, `capabilities`,
`context_window`, `cost_profile`, `local_or_cloud`, and `availability`.
Providers declare their own model lists — nothing in the Router or Gateway
hardcodes provider-specific behavior.

### Capabilities (`capabilities.py`)

A `ModelCapabilities` dataclass of boolean flags: `text_generation`,
`vision`, `tool_calling`, `structured_output`, `streaming`, `embeddings`,
`reasoning`, `realtime_audio_session`, `local_execution`. The Router uses
`capabilities.supports(*required)` to filter candidates. Nothing assumes
every provider/model supports every capability — e.g. the Ollama adapter
does **not** claim `tool_calling=True` by default, since that varies by
which local model is actually pulled.

### Request/response types (`types.py`)

`ModelRequest` (messages, system_instruction, tools, stream, session_mode,
metadata) and `ModelResponse` (content, content_blocks, tool_calls, usage,
finish_reason) are provider-neutral. `StreamEvent` covers incremental
streaming. These types intentionally do **not** try to model Gemini Live's
realtime audio session — see below.

### Provider Registry (`registry.py`)

Providers are registered as factories, not instances — nothing is
constructed (no client created, no network touched) until first use
(`get_default_registry()` wires up Gemini/Ollama/OpenAI-compatible/OpenAI/
Anthropic against Phase 1's `ConfigService`, lazily). `health_check_all()`
never raises — an unconfigured/unhealthy provider is reported, not fatal.

### Model Router (`router.py`)

Rule-based (not an LLM router agent — Phase 2 explicitly defers that).
Selection order for `route(task_type, required_capabilities, privacy,
override_provider, override_model)`:

1. **Explicit override**, if given and available.
2. **Privacy=local** forces routing to a local-only provider (Ollama /
   OpenAI-compatible), raising `NoCompatibleModelError` if none is available
   — it does not silently fall back to a cloud provider.
3. **User-configured task route**, read from `ConfigService` at keys like
   `routing.coding.provider` / `routing.coding.model`, if set.
4. **Built-in default task table** (`_DEFAULT_TASK_ROUTES`): `default`,
   `planner`, `coding`, `vision`, `fast` → Gemini; `local`/`private` → Ollama.
5. **Global fallback chain**: Gemini → Ollama → OpenAI-compatible.

If nothing satisfies the required capabilities, `NoCompatibleModelError` is
raised with a clear message — never a silent wrong answer.

### Model Gateway (`gateway.py`)

Wraps a Router decision with retry (`RetryPolicy`) and fallback
(`FallbackPolicy`) behavior:

- Retries only `ModelError` subclasses with `retryable = True` (rate limits,
  timeouts, connection errors) — never retries authentication, capability,
  or configuration errors, since retrying those can't help.
- On exhaustion or a `ModelUnavailableError`, tries the configured
  fallback chain (default: try Ollama, then Gemini, excluding whichever
  provider just failed).
- `generate_text(prompt, system=None, task_type="default", tools=None)` is
  the convenience entry point most `actions/*.py` modules now use — it
  replaced ~10 separate `genai.Client()` + `generate_content()` call sites.

### Provider adapters

| Adapter | File | Status |
|---|---|---|
| Gemini | `providers/gemini.py` | **Supported** — standard (non-Live) calls |
| Gemini Live | `providers/gemini_live.py` | **Supported** — specialized, see below |
| Ollama | `providers/ollama.py` | **Supported** — chat, streaming, health check |
| OpenAI-compatible | `providers/openai_compatible.py` | **Supported** — LM Studio/Jan/LocalAI/vLLM |
| OpenAI | `providers/openai.py` | **Partially implemented** — wraps the OpenAI-compatible adapter against `api.openai.com`; no OpenAI-specific features (Responses API, o-series params) yet |
| Anthropic | `providers/anthropic.py` | **Planned** — architectural skeleton only; `generate()` raises `NotImplementedError`, `is_configured()` returns `False` |

See `docs/providers.md` for the user-facing version of this table.

## Gemini Live: the deliberate exception

Gemini Live is a persistent, bidirectional, audio-streaming session — not a
`generate(request) -> response` call. Forcing it through `ModelGateway`
would either break its streaming semantics or require a fake synchronous
wrapper that lies about what's happening. So it has its own class,
`GeminiLiveAdapter` (`providers/gemini_live.py`), which is the **one**
place in the codebase still allowed to call `google.genai` directly — it
*is* the provider boundary for realtime audio.

`GeminiLiveAdapter.connect(model, config)` is an async context manager that
constructs a fresh `genai.Client` and calls `client.aio.live.connect(...)`,
returning the native session object exactly as before. `main.py`'s
send/receive/audio-queue loop (`_send_realtime`, `_listen_audio`,
`_receive_audio`, `_play_audio`, interrupt handling) is **completely
unchanged** — it just gets its `session` from the adapter instead of
building the client inline. `actions/screen_processor.py`'s separate Live
session (used for on-demand screen/camera vision queries) is wrapped the
same way.

This is why `RetryPolicy` explicitly does not apply to realtime
sessions — retrying a `connect()` through the Gateway's retry loop could
create multiple concurrent Live sessions, which the spec calls out as a
hazard to avoid.

## What's still direct-SDK (and why)

A few call sites still use `google.genai` directly, deliberately:

- **Vision/image-input calls** (`code_helper.py`'s screen-debug analysis,
  `computer_control.py`'s `_screen_find`, `file_processor.py`'s image
  analysis paths, some paths in `dev_agent.py`): `ModelRequest` only models
  text messages today. Rather than rush an image-content type into Phase 2,
  these keep working exactly as before; a future phase can extend
  `ModelRequest`/`ContentBlock` to carry image parts and migrate them.
- **Gemini's built-in Google Search grounding tool** (`web_search.py`'s
  `_gemini_search`/`_gemini_headlines`): this is a Gemini-specific
  server-side tool (`config={"tools": [{"google_search": {}}]}`), not a
  portable capability other providers expose the same way — routing it
  through the generic Gateway would misrepresent it as provider-neutral
  when it isn't.

Both cases have a `_get_model()`/`_gemini_client()`-style wrapper that
routes **plain string prompts** through the Gateway and only falls back to
direct SDK usage for non-string (image-bearing) `contents` — see
`dev_agent.py`, `code_helper.py`, and `file_processor.py` for the pattern.

## Error taxonomy (`errors.py`)

Provider-specific exceptions are translated at the adapter boundary into:
`AuthenticationError`, `RateLimitError`, `TimeoutError`, `ConnectionError`
(all retryable except `AuthenticationError`), and `CapabilityError`,
`ConfigurationError`, `ModelUnavailableError`, `ProviderError` (not
retryable). The Gateway only ever needs to handle this one hierarchy.

## What Phase 2 does NOT do

- No Tool Registry (Phase 3) — `main.py`'s `TOOL_DECLARATIONS` /
  `_execute_tool` 19-branch dispatcher is untouched.
- No multi-agent orchestration (Phase 4).
- No memory rebuild (Phase 5).
- No sandbox/security rebuild (Phase 6) — the Gateway doesn't add any new
  code-execution path.
- No LLM-based "router agent" — routing is plain rule-based Python.
