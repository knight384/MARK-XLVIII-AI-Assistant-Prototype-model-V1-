"""
core.llm.providers.anthropic — Anthropic provider adapter.

Status: PLANNED / SKELETON ONLY (Phase 2 spec, Part 12). This establishes
the extension point (registry entry, capability declaration, config keys)
without a working `generate()` implementation, so a future phase can fill
it in without touching the Router/Gateway. Calling `generate()` or
`health_check()` on this provider does NOT silently pretend to work — it
reports itself as unavailable / raises clearly, rather than faking a
response (Part 12: "Do not fake functionality.").
"""
from __future__ import annotations

from ..capabilities import ModelCapabilities
from .base import HealthStatus, ModelInfo, Provider


class AnthropicProvider(Provider):
    provider_id = "anthropic"
    display_name = "Anthropic (planned — not yet implemented)"

    def __init__(self, api_key_getter=None, model_getter=None):
        self._api_key_getter = api_key_getter
        self._model_getter = model_getter or (lambda: "claude-sonnet-4-6")

    def is_configured(self) -> bool:
        return False  # deliberately: no working generate() to configure toward yet

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                model_id=self._model_getter(), provider_id=self.provider_id,
                display_name="Anthropic Claude (not yet implemented)",
                capabilities=ModelCapabilities(
                    text_generation=True, vision=True, tool_calling=True,
                    structured_output=True, streaming=True, reasoning=True,
                ),
                cost_profile="unknown", local_or_cloud="cloud", availability="unavailable",
            )
        ]

    def health_check(self) -> HealthStatus:
        return HealthStatus(
            healthy=False,
            detail="Anthropic adapter is a Phase 2 architectural placeholder — "
                   "generate() is not implemented yet.",
        )

    def generate(self, request, model_id: str):
        raise NotImplementedError(
            "AnthropicProvider.generate() is not implemented — this is a Phase 2 "
            "architecture placeholder only (see module docstring)."
        )
