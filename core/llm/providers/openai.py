"""
core.llm.providers.openai — official OpenAI API adapter.

Status: PARTIALLY IMPLEMENTED (Phase 2 spec, Part 11). OpenAI's
`/v1/chat/completions` semantics are close enough to the generic
OpenAI-compatible adapter that this wraps it rather than duplicating request/
response handling, pointed at `https://api.openai.com` with a required API
key. What's NOT done here: OpenAI-specific features (the Responses API,
native structured outputs via `response_format={"type":"json_schema"}`,
o-series reasoning params, etc.) — those would need genuine OpenAI-specific
handling, deliberately left out to avoid unnecessarily expanding this phase
(spec Part 11: "Do not add unnecessary complexity").
"""
from __future__ import annotations

from ..capabilities import ModelCapabilities
from ..errors import AuthenticationError
from .base import HealthStatus, ModelInfo
from .openai_compatible import OpenAICompatibleProvider

_DEFAULT_BASE_URL = "https://api.openai.com"


class OpenAIProvider(OpenAICompatibleProvider):
    provider_id = "openai"
    display_name = "OpenAI"

    def __init__(self, api_key_getter, model_getter):
        super().__init__(
            base_url_getter=lambda: _DEFAULT_BASE_URL,
            model_getter=model_getter,
            api_key_getter=api_key_getter,
        )

    def is_configured(self) -> bool:
        try:
            return bool(self._api_key_getter and self._api_key_getter())
        except Exception:
            return False

    def list_models(self) -> list[ModelInfo]:
        model = self._model_getter()
        return [
            ModelInfo(
                model_id=model, provider_id=self.provider_id, display_name=f"OpenAI: {model}",
                capabilities=ModelCapabilities(
                    text_generation=True, tool_calling=True, streaming=True, structured_output=True,
                ),
                cost_profile="medium", local_or_cloud="cloud",
            )
        ]

    def health_check(self) -> HealthStatus:
        if not self.is_configured():
            return HealthStatus(healthy=False, detail="OpenAI API key not configured.")
        # No network call at health-check time (Part 29) — mirrors GeminiProvider's approach.
        return HealthStatus(healthy=True, detail="API key configured.")
