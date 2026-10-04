# Supported AI Providers

Status legend: **SUPPORTED** (working, tested with mocks, used in the app) ·
**PARTIALLY IMPLEMENTED** (works for basic calls, missing provider-specific
features) · **PLANNED** (architecture exists, no working implementation yet).

| Provider | Status | Notes |
|---|---|---|
| **Google Gemini** | SUPPORTED | Standard (non-realtime) text/coding calls, routed through the Model Gateway. Configure via the app's setup wizard (stores your key through Phase 1's secure config service). |
| **Google Gemini Live** | SUPPORTED | The realtime voice assistant. Uses a specialized adapter (`GeminiLiveAdapter`), not the generic Gateway — see `docs/architecture/model-gateway.md`. This is JARVIS's primary interaction mode and is unchanged by Phase 2. |
| **Ollama** | SUPPORTED | Local models via `http://localhost:11434` by default. Configure `llm_url`/`llm_model` via `ConfigService` (e.g. through the setup wizard's local-LLM fields). Tool-calling support depends on which model you've pulled — not assumed by default. |
| **OpenAI-compatible** | SUPPORTED | Any server speaking the `/v1/chat/completions` API — LM Studio, Jan, LocalAI, vLLM, llama.cpp server, etc. Configure `llm_url`/`llm_model` the same way as Ollama; select this provider instead of Ollama when your local server uses the OpenAI wire format. |
| **OpenAI (official, api.openai.com)** | PARTIALLY IMPLEMENTED | Basic chat completions work once an `openai_api_key` secret is configured. Not yet implemented: OpenAI-specific features (Responses API, native `json_schema` structured outputs, o-series reasoning parameters). |
| **Anthropic** | PLANNED | Architectural placeholder only (`core/llm/providers/anthropic.py`). `is_configured()` always returns `False` and `generate()` raises `NotImplementedError` — it is registered in the provider registry so the Router/Gateway machinery is ready, but there is no working call path yet. |

## How to select a provider

Most of this is currently configuration-only (no dedicated UI yet — that's
a later phase, per the Phase 2 spec's "no premature UI work"):

```python
from core.config import get_config_service
config = get_config_service()

config.set("llm_provider", "ollama")           # or "openai_compatible"
config.set("llm_url", "http://localhost:11434")
config.set("llm_model", "llama3.2")
```

For an explicit one-off override on a single call:

```python
from core.llm.gateway import get_default_gateway
from core.llm.types import Message, ModelRequest

gateway = get_default_gateway()
response = gateway.generate(
    ModelRequest(messages=[Message(role="user", content="hello")]),
    provider_id="ollama", model_id="llama3.2",
)
```

## Capability differences

Not every provider/model supports the same things. Check before assuming:

```python
from core.llm.registry import get_default_registry

registry = get_default_registry()
for model in registry.all_models():
    print(model.provider_id, model.model_id, model.capabilities)
```

Vision, tool-calling, and structured-output support vary — the Router will
raise `NoCompatibleModelError` rather than silently using a model that can't
actually do what was asked.
