"""
core.llm.providers.gemini — standard (non-realtime) Gemini adapter.

This is the ONE place in the codebase that should call
`google.genai.Client(...).models.generate_content(...)` for ordinary
request/response calls. Gemini Live (the voice session) is a separate,
specialized adapter — see gemini_live.py — because it is not a
request/response API.
"""
from __future__ import annotations

import logging
import time

from ..capabilities import ModelCapabilities
from ..errors import (
    AuthenticationError, CapabilityError, ConfigurationError,
    ConnectionError as LLMConnectionError, ModelError, ProviderError,
    RateLimitError, TimeoutError as LLMTimeoutError,
)
from ..types import ContentBlock, Message, ModelRequest, ModelResponse, ToolCall, Usage
from .base import HealthStatus, ModelInfo, Provider

logger = logging.getLogger(__name__)

_MODELS = [
    ModelInfo(
        model_id="gemini-2.5-flash", provider_id="gemini", display_name="Gemini 2.5 Flash",
        capabilities=ModelCapabilities(
            text_generation=True, vision=True, tool_calling=True,
            structured_output=True, streaming=True, reasoning=True,
        ),
        context_window=1_000_000, cost_profile="low", local_or_cloud="cloud",
    ),
    ModelInfo(
        model_id="gemini-2.5-flash-lite", provider_id="gemini", display_name="Gemini 2.5 Flash Lite",
        capabilities=ModelCapabilities(
            text_generation=True, vision=False, tool_calling=True,
            structured_output=True, streaming=True,
        ),
        context_window=1_000_000, cost_profile="low", local_or_cloud="cloud",
    ),
]


class GeminiProvider(Provider):
    provider_id = "gemini"
    display_name = "Google Gemini"

    def __init__(self, api_key_getter):
        """api_key_getter: zero-arg callable returning the Gemini API key
        (normally `core.config.get_config_service().get_gemini_api_key`).
        Injected rather than read directly here so this module has no
        dependency on *how* the key is stored (Phase 1 concern, not Phase 2's)."""
        self._api_key_getter = api_key_getter
        self._client = None  # lazy — Part 29: avoid unnecessary init at startup

    def _get_client(self):
        if self._client is None:
            try:
                api_key = self._api_key_getter()
            except Exception as exc:
                raise AuthenticationError(
                    "Gemini API key not available.", provider=self.provider_id, cause=exc,
                ) from exc
            from google import genai
            self._client = genai.Client(api_key=api_key)
        return self._client

    def list_models(self) -> list[ModelInfo]:
        return list(_MODELS)

    def is_configured(self) -> bool:
        try:
            self._api_key_getter()
            return True
        except Exception:
            return False

    def health_check(self) -> HealthStatus:
        if not self.is_configured():
            return HealthStatus(healthy=False, detail="Gemini API key not configured.")
        # Deliberately no network call here (Part 29) — "configured" is the
        # cheap, useful signal; a bad key still surfaces on first real call.
        return HealthStatus(healthy=True, detail="API key configured.",
                             checked_models=[m.model_id for m in _MODELS])

    def generate(self, request: ModelRequest, model_id: str) -> ModelResponse:
        model_info = self.get_model(model_id)
        if request.tools and (not model_info or not model_info.capabilities.tool_calling):
            raise CapabilityError(
                f"Model '{model_id}' does not support tool calling.",
                provider=self.provider_id, model=model_id,
            )

        client = self._get_client()
        contents = self._to_gemini_contents(request)

        t0 = time.perf_counter()
        try:
            kwargs = {"model": model_id, "contents": contents}
            config = self._build_config(request)
            if config is not None:
                kwargs["config"] = config
            response = client.models.generate_content(**kwargs)
        except Exception as exc:
            raise self._translate_error(exc, model_id) from exc
        latency_ms = (time.perf_counter() - t0) * 1000

        text = getattr(response, "text", "") or ""
        return ModelResponse(
            content=text,
            content_blocks=[ContentBlock(type="text", text=text)] if text else [],
            usage=Usage(),  # google.genai's usage_metadata shape varies by SDK version; left unset rather than guessed
            finish_reason="stop",
            model=model_id,
            provider=self.provider_id,
            latency_ms=latency_ms,
        )

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _to_gemini_contents(request: ModelRequest):
        """Flattens provider-neutral messages into a single prompt string.
        This mirrors what most existing call sites in this repo already do
        (single-turn `model.generate_content(prompt)` calls) — multi-turn
        native `Content`/`Part` objects can be added later without changing
        this adapter's external interface."""
        parts = []
        if request.system_instruction:
            parts.append(request.system_instruction)
        for msg in request.messages:
            if msg.role == "system":
                parts.append(msg.content)
            else:
                parts.append(msg.content)
        return "\n\n".join(parts)

    @staticmethod
    def _build_config(request: ModelRequest):
        if not request.tools:
            return None
        try:
            from google.genai import types
            return types.GenerateContentConfig(
                tools=[{"function_declarations": request.tools}],
            )
        except Exception:
            return None

    def _translate_error(self, exc: Exception, model_id: str) -> ModelError:
        msg = str(exc)
        lower = msg.lower()
        kwargs = dict(provider=self.provider_id, model=model_id, cause=exc)
        if "api key" in lower or "unauthorized" in lower or "permission" in lower or "401" in lower or "403" in lower:
            return AuthenticationError(msg, **kwargs)
        if "rate limit" in lower or "429" in lower or "quota" in lower:
            return RateLimitError(msg, **kwargs)
        if "timeout" in lower or "timed out" in lower:
            return LLMTimeoutError(msg, **kwargs)
        if "connection" in lower or "network" in lower or "unreachable" in lower:
            return LLMConnectionError(msg, **kwargs)
        return ProviderError(msg, **kwargs)
