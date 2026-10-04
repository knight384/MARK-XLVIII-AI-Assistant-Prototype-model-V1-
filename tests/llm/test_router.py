"""tests/llm/test_router.py — Model Router scenario tests (Phase 2 spec, Part 31)."""
from __future__ import annotations

import pytest

from .conftest import FakeProvider, make_model
from core.llm.router import ModelRouter, NoCompatibleModelError


def test_default_routes_to_gemini_when_available(empty_registry):
    gemini = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash", tool_calling=True)])
    empty_registry.register("gemini", lambda: gemini)
    router = ModelRouter(empty_registry)

    decision = router.route("default")
    assert decision.provider_id == "gemini"
    assert decision.model_id == "gemini-2.5-flash"


def test_local_only_routes_to_ollama(empty_registry):
    ollama = FakeProvider("ollama", [make_model("ollama", "llama3.2", local_execution=True)])
    empty_registry.register("ollama", lambda: ollama)
    router = ModelRouter(empty_registry)

    decision = router.route(privacy="local")
    assert decision.provider_id == "ollama"


def test_privacy_local_raises_when_no_local_provider(empty_registry):
    gemini = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash")])
    empty_registry.register("gemini", lambda: gemini)  # cloud only, no local provider registered
    router = ModelRouter(empty_registry)

    with pytest.raises(NoCompatibleModelError):
        router.route(privacy="local")


def test_vision_requires_vision_capability(empty_registry):
    vision_model = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash", vision=True)])
    empty_registry.register("gemini", lambda: vision_model)
    router = ModelRouter(empty_registry)

    decision = router.route("vision", required_capabilities=("vision",))
    assert decision.provider_id == "gemini"
    assert decision.capabilities.vision is True


def test_vision_fails_when_no_vision_capable_model(empty_registry):
    text_only = FakeProvider("ollama", [make_model("ollama", "llama3.2")])  # no vision
    empty_registry.register("ollama", lambda: text_only)
    router = ModelRouter(empty_registry)

    with pytest.raises(NoCompatibleModelError):
        router.route("vision", required_capabilities=("vision",))


def test_explicit_override_wins(empty_registry):
    gemini = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash")])
    ollama = FakeProvider("ollama", [make_model("ollama", "llama3.2")])
    empty_registry.register("gemini", lambda: gemini)
    empty_registry.register("ollama", lambda: ollama)
    router = ModelRouter(empty_registry)

    decision = router.route("default", override_provider="ollama", override_model="llama3.2")
    assert decision.provider_id == "ollama"
    assert decision.reason == "explicit user override"


def test_override_falls_back_when_unavailable(empty_registry):
    gemini = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash")])
    empty_registry.register("gemini", lambda: gemini)
    # No "nonexistent" provider registered at all.
    router = ModelRouter(empty_registry)

    decision = router.route("default", override_provider="nonexistent", override_model="x")
    assert decision.provider_id == "gemini"  # fell through to normal routing


def test_unconfigured_provider_is_skipped(empty_registry):
    unconfigured = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash")], configured=False)
    ollama = FakeProvider("ollama", [make_model("ollama", "llama3.2")], configured=True)
    empty_registry.register("gemini", lambda: unconfigured)
    empty_registry.register("ollama", lambda: ollama)
    router = ModelRouter(empty_registry)

    decision = router.route("default")
    assert decision.provider_id == "ollama"  # gemini skipped for being unconfigured


def test_no_compatible_model_raises_clear_error(empty_registry):
    router = ModelRouter(empty_registry)  # nothing registered at all
    with pytest.raises(NoCompatibleModelError):
        router.route("default")


def test_user_configured_task_route_takes_priority(empty_registry):
    gemini = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash")])
    ollama = FakeProvider("ollama", [make_model("ollama", "custom-model", tool_calling=True)])
    empty_registry.register("gemini", lambda: gemini)
    empty_registry.register("ollama", lambda: ollama)

    class FakeConfig:
        def get(self, key, default=None):
            if key == "routing.coding.provider":
                return "ollama"
            if key == "routing.coding.model":
                return "custom-model"
            return default

    router = ModelRouter(empty_registry, config=FakeConfig())
    decision = router.route("coding", required_capabilities=())
    assert decision.provider_id == "ollama"
    assert decision.model_id == "custom-model"
