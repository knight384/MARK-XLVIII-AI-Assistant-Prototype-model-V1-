"""
tests/llm/conftest.py — shared fixtures for the Phase 2 Model Gateway test suite.

All provider tests use fakes/mocks — no real API keys, no real network calls
(Phase 2 spec, Part 32).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.llm.capabilities import ModelCapabilities
from core.llm.providers.base import HealthStatus, ModelInfo, Provider
from core.llm.registry import ProviderRegistry
from core.llm.types import ContentBlock, ModelRequest, ModelResponse, Usage


class FakeProvider(Provider):
    """A minimal, fully-controllable fake Provider for testing the Router
    and Gateway without touching any real SDK/network."""

    def __init__(self, provider_id: str, models: list[ModelInfo],
                 configured: bool = True, healthy: bool = True,
                 raise_on_generate: Exception | None = None,
                 response_text: str = "fake response"):
        self.provider_id = provider_id
        self.display_name = f"Fake {provider_id}"
        self._models = models
        self._configured = configured
        self._healthy = healthy
        self._raise_on_generate = raise_on_generate
        self._response_text = response_text
        self.generate_calls: list[tuple[ModelRequest, str]] = []

    def list_models(self) -> list[ModelInfo]:
        return list(self._models)

    def is_configured(self) -> bool:
        return self._configured

    def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=self._healthy, detail="fake")

    def generate(self, request: ModelRequest, model_id: str) -> ModelResponse:
        self.generate_calls.append((request, model_id))
        if self._raise_on_generate:
            raise self._raise_on_generate
        return ModelResponse(
            content=self._response_text,
            content_blocks=[ContentBlock(type="text", text=self._response_text)],
            usage=Usage(),
            finish_reason="stop",
            model=model_id,
            provider=self.provider_id,
        )


def make_model(provider_id: str, model_id: str, **cap_kwargs) -> ModelInfo:
    caps = ModelCapabilities(text_generation=True, **cap_kwargs)
    return ModelInfo(model_id=model_id, provider_id=provider_id,
                      display_name=model_id, capabilities=caps)


@pytest.fixture
def empty_registry() -> ProviderRegistry:
    return ProviderRegistry()
