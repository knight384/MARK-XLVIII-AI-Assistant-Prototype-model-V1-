"""tests/llm/test_registry.py — provider registration/lookup/health checks."""
from __future__ import annotations

from .conftest import FakeProvider, make_model


def test_register_and_get(empty_registry):
    provider = FakeProvider("fake", [make_model("fake", "m1")])
    empty_registry.register("fake", lambda: provider)
    assert empty_registry.get("fake") is provider


def test_get_unregistered_returns_none(empty_registry):
    assert empty_registry.get("nonexistent") is None


def test_lazy_construction_only_once(empty_registry):
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return FakeProvider("fake", [make_model("fake", "m1")])

    empty_registry.register("fake", factory)
    empty_registry.get("fake")
    empty_registry.get("fake")
    empty_registry.get("fake")
    assert calls["n"] == 1  # constructed once, cached thereafter


def test_find_model_across_providers(empty_registry):
    p1 = FakeProvider("p1", [make_model("p1", "model-a")])
    p2 = FakeProvider("p2", [make_model("p2", "model-b")])
    empty_registry.register("p1", lambda: p1)
    empty_registry.register("p2", lambda: p2)

    found = empty_registry.find_model("model-b")
    assert found is not None
    provider, info = found
    assert provider is p2
    assert info.model_id == "model-b"


def test_find_model_not_found(empty_registry):
    empty_registry.register("p1", lambda: FakeProvider("p1", [make_model("p1", "model-a")]))
    assert empty_registry.find_model("nonexistent-model") is None


def test_health_check_all_never_raises(empty_registry):
    healthy = FakeProvider("healthy", [make_model("healthy", "m1")], healthy=True)
    unhealthy = FakeProvider("unhealthy", [make_model("unhealthy", "m2")], healthy=False)

    def broken_factory():
        raise RuntimeError("construction failed")

    empty_registry.register("healthy", lambda: healthy)
    empty_registry.register("unhealthy", lambda: unhealthy)
    empty_registry.register("broken", broken_factory)

    results = empty_registry.health_check_all()
    assert results["healthy"].healthy is True
    assert results["unhealthy"].healthy is False
    assert results["broken"].healthy is False  # construction failure reported, not raised


def test_all_models(empty_registry):
    empty_registry.register("p1", lambda: FakeProvider("p1", [make_model("p1", "a"), make_model("p1", "b")]))
    empty_registry.register("p2", lambda: FakeProvider("p2", [make_model("p2", "c")]))
    models = empty_registry.all_models()
    assert {m.model_id for m in models} == {"a", "b", "c"}
