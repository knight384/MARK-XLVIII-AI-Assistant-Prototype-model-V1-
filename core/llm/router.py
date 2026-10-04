"""
core.llm.router — rule-based Model Router (Phase 2 spec, Parts 15-18).

Deliberately rule-based, not an "LLM router agent" (Part 18: "Do NOT
introduce an LLM-based router agent yet"). Supports fixed, capability-based,
hybrid (privacy-aware), and fallback routing modes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .registry import ProviderRegistry
from .providers.base import ModelInfo
from .tiers import ModelTier

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    provider_id: str
    model_id: str
    capabilities: object   # ModelCapabilities — kept loosely typed to avoid an import cycle
    reason: str


class NoCompatibleModelError(Exception):
    """Raised when the router cannot find any provider/model satisfying the
    request (Part 18: 'No compatible model → clear error')."""


# Task-type -> preferred (provider_id, model_id) list, in priority order.
# This is the "capability mode" / "hybrid mode" default policy table
# (Part 18). Users can override any of this via ConfigService (Part 16) or
# an explicit per-call override (Part 17).
_DEFAULT_TASK_ROUTES: dict[str, list[tuple[str, str]]] = {
    "default":  [("gemini", "gemini-2.5-flash")],
    "planner":  [("gemini", "gemini-2.5-flash")],
    ModelTier.FAST.value:      [("gemini", "gemini-2.5-flash-lite")],
    ModelTier.STANDARD.value:  [("gemini", "gemini-2.5-flash")],
    ModelTier.REASONING.value: [("gemini", "gemini-2.5-pro")],
    ModelTier.CODING.value:    [("gemini", "gemini-2.5-flash")],
    ModelTier.VISION.value:    [("gemini", "gemini-2.5-flash")],
    ModelTier.REALTIME.value:  [("gemini", "gemini-2.5-flash-native-audio-preview")],
    ModelTier.EMBEDDING.value: [("gemini", "text-embedding-004")],
    ModelTier.LOCAL.value:     [("ollama", None)],
    "private":  [("ollama", None)],
}

_REQUIRED_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "vision": ("vision",),
    "coding": ("tool_calling",),
}


class ModelRouter:
    def __init__(self, registry: ProviderRegistry, config=None):
        self._registry = registry
        self._config = config  # optional ConfigService, for user-configured routing overrides

    def route(
        self,
        task_type: str | ModelTier = "default",
        *,
        required_capabilities: tuple[str, ...] = (),
        privacy: str | None = None,           # "local" forces local-only routing
        override_provider: str | None = None,
        override_model: str | None = None,
    ) -> RoutingDecision:
        if isinstance(task_type, ModelTier):
            task_type = task_type.value
        # 1. Explicit override always wins if the target is actually available (Part 17).
        if override_provider:
            decision = self._try_explicit(override_provider, override_model, reason="explicit user override")
            if decision:
                return decision
            logger.warning(
                "Requested provider/model override ('%s'/'%s') is unavailable — falling back to routing.",
                override_provider, override_model,
            )

        required = set(required_capabilities) | set(_REQUIRED_CAPABILITIES.get(task_type, ()))

        # 2. Privacy-forced local routing (hybrid mode, Part 18).
        if privacy == "local":
            decision = self._try_route_list([("ollama", None), ("openai_compatible", None)],
                                             required, reason="privacy=local")
            if decision:
                return decision
            raise NoCompatibleModelError("privacy=local requested but no local provider is available/healthy.")

        # 3. User-configured task route (Part 16), falling back to the built-in default table.
        candidates = self._configured_route(task_type) or _DEFAULT_TASK_ROUTES.get(
            task_type, _DEFAULT_TASK_ROUTES["default"]
        )
        decision = self._try_route_list(candidates, required, reason=f"task_type='{task_type}'")
        if decision:
            return decision

        # 4. Global fallback chain (Part 20).
        fallback_candidates = [("gemini", "gemini-2.5-flash"), ("ollama", None), ("openai_compatible", None)]
        decision = self._try_route_list(fallback_candidates, required, reason="global fallback")
        if decision:
            return decision

        raise NoCompatibleModelError(
            f"No available provider/model satisfies task_type='{task_type}' "
            f"with required capabilities={sorted(required)}."
        )

    # -- internals ------------------------------------------------------

    def _configured_route(self, task_type: str) -> list[tuple[str, str]] | None:
        if not self._config:
            return None
        provider_id = self._config.get(f"routing.{task_type}.provider")
        model_id = self._config.get(f"routing.{task_type}.model")
        if provider_id:
            return [(provider_id, model_id)]
        return None

    def _try_explicit(self, provider_id: str, model_id: str | None, reason: str) -> RoutingDecision | None:
        provider = self._registry.get(provider_id)
        if provider is None or not provider.is_configured():
            return None
        resolved_model = model_id or self._default_model_for(provider_id)
        info = provider.get_model(resolved_model) if resolved_model else None
        capabilities = info.capabilities if info else None
        return RoutingDecision(provider_id=provider_id, model_id=resolved_model,
                                capabilities=capabilities, reason=reason)

    def _try_route_list(self, candidates: list[tuple[str, str | None]],
                         required: set[str], reason: str) -> RoutingDecision | None:
        for provider_id, model_id in candidates:
            provider = self._registry.get(provider_id)
            if provider is None or not provider.is_configured():
                continue
            resolved_model = model_id or self._default_model_for(provider_id)
            if not resolved_model:
                continue
            info = provider.get_model(resolved_model)
            if info is None:
                continue
            if required and not info.capabilities.supports(*required):
                continue
            return RoutingDecision(provider_id=provider_id, model_id=resolved_model,
                                    capabilities=info.capabilities, reason=reason)
        return None

    def _default_model_for(self, provider_id: str) -> str | None:
        provider = self._registry.get(provider_id)
        if provider is None:
            return None
        models = provider.list_models()
        return models[0].model_id if models else None
