"""
core.llm.registry — provider registry (Phase 2 spec, Part 13).

Providers are constructed lazily: registering a provider only stores a
factory function, not an instantiated client (Part 29 — "do not instantiate
every expensive provider connection at startup unnecessarily"). The default
registry (`get_default_registry()`) wires up Gemini, Gemini Live, Ollama,
OpenAI-compatible, OpenAI, and Anthropic against Phase 1's ConfigService, but
nothing is actually constructed until first use.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from .providers.base import HealthStatus, ModelInfo, Provider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    def __init__(self):
        self._factories: dict[str, Callable[[], Provider]] = {}
        self._instances: dict[str, Provider] = {}
        self._lock = threading.Lock()

    def register(self, provider_id: str, factory: Callable[[], Provider]) -> None:
        with self._lock:
            self._factories[provider_id] = factory
            self._instances.pop(provider_id, None)  # force re-construction if re-registered

    def get(self, provider_id: str) -> Provider | None:
        with self._lock:
            if provider_id in self._instances:
                return self._instances[provider_id]
            factory = self._factories.get(provider_id)
            if factory is None:
                return None
            try:
                instance = factory()
            except Exception as exc:
                logger.error("Failed to construct provider '%s': %s", provider_id, exc)
                return None
            self._instances[provider_id] = instance
            return instance

    def list_provider_ids(self) -> list[str]:
        return list(self._factories.keys())

    def find_model(self, model_id: str) -> tuple[Provider, ModelInfo] | None:
        for provider_id in self.list_provider_ids():
            provider = self.get(provider_id)
            if provider is None:
                continue
            info = provider.get_model(model_id)
            if info is not None:
                return provider, info
        return None

    def all_models(self) -> list[ModelInfo]:
        out: list[ModelInfo] = []
        for provider_id in self.list_provider_ids():
            provider = self.get(provider_id)
            if provider is None:
                continue
            try:
                out.extend(provider.list_models())
            except Exception as exc:
                logger.warning("list_models() failed for provider '%s': %s", provider_id, exc)
        return out

    def health_check_all(self) -> dict[str, HealthStatus]:
        """Never raises — an unavailable/unconfigured provider is reported,
        not fatal (Part 19: 'JARVIS should still work using Gemini.')."""
        results: dict[str, HealthStatus] = {}
        for provider_id in self.list_provider_ids():
            provider = self.get(provider_id)
            if provider is None:
                results[provider_id] = HealthStatus(healthy=False, detail="Failed to construct provider.")
                continue
            try:
                results[provider_id] = provider.health_check()
            except Exception as exc:
                results[provider_id] = HealthStatus(healthy=False, detail=f"health_check() raised: {exc}")
        return results


_default_registry: ProviderRegistry | None = None
_default_lock = threading.Lock()


def get_default_registry() -> ProviderRegistry:
    """The application-wide registry, wired against Phase 1's ConfigService.
    Constructed once, lazily, on first call."""
    global _default_registry
    with _default_lock:
        if _default_registry is not None:
            return _default_registry

        from core.config import get_config_service
        config = get_config_service()

        registry = ProviderRegistry()

        registry.register("gemini", lambda: _build_gemini(config))
        registry.register("ollama", lambda: _build_ollama(config))
        registry.register("openai_compatible", lambda: _build_openai_compatible(config))
        registry.register("openai", lambda: _build_openai(config))
        registry.register("anthropic", lambda: _build_anthropic(config))

        _default_registry = registry
        return registry


def _build_gemini(config):
    from .providers.gemini import GeminiProvider
    return GeminiProvider(api_key_getter=config.get_gemini_api_key)


def _build_ollama(config):
    from .providers.ollama import OllamaProvider
    return OllamaProvider(
        base_url_getter=lambda: config.get("llm_url", "http://localhost:11434"),
        model_getter=lambda: config.get("llm_model", "llama3.2"),
    )


def _build_openai_compatible(config):
    from .providers.openai_compatible import OpenAICompatibleProvider
    return OpenAICompatibleProvider(
        base_url_getter=lambda: config.get("llm_url", "http://localhost:1234"),
        model_getter=lambda: config.get("llm_model", "local-model"),
    )


def _build_openai(config):
    from .providers.openai import OpenAIProvider
    return OpenAIProvider(
        api_key_getter=lambda: config.get_secret("openai_api_key"),
        model_getter=lambda: config.get("openai_model", "gpt-4o-mini"),
    )


def _build_anthropic(config):
    from .providers.anthropic import AnthropicProvider
    return AnthropicProvider(
        api_key_getter=lambda: config.get_secret("anthropic_api_key"),
        model_getter=lambda: config.get("anthropic_model", "claude-sonnet-4-6"),
    )
