"""tests/llm/test_gateway.py — Gateway retry/fallback behavior."""
from __future__ import annotations

from .conftest import FakeProvider, make_model

from core.llm.errors import AuthenticationError, ModelUnavailableError, RateLimitError
from core.llm.gateway import ModelGateway
from core.llm.policies import FallbackPolicy, RetryPolicy
from core.llm.router import ModelRouter
from core.llm.types import Message, ModelRequest


def _simple_request() -> ModelRequest:
    return ModelRequest(messages=[Message(role="user", content="hello")])


def test_successful_generate(empty_registry):
    gemini = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash")], response_text="hi there")
    empty_registry.register("gemini", lambda: gemini)
    gateway = ModelGateway(registry=empty_registry, router=ModelRouter(empty_registry))

    response = gateway.generate(_simple_request())
    assert response.content == "hi there"
    assert len(gemini.generate_calls) == 1


def test_retries_on_retryable_error_then_succeeds(empty_registry):
    calls = {"n": 0}

    class FlakyProvider(FakeProvider):
        def generate(self, request, model_id):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RateLimitError("rate limited", provider="gemini", model=model_id)
            return super().generate(request, model_id)

    flaky = FlakyProvider("gemini", [make_model("gemini", "gemini-2.5-flash")], response_text="ok now")
    empty_registry.register("gemini", lambda: flaky)
    gateway = ModelGateway(registry=empty_registry, router=ModelRouter(empty_registry),
                            retry_policy=RetryPolicy(max_attempts=3, backoff_base_s=0.001))

    response = gateway.generate(_simple_request())
    assert response.content == "ok now"
    assert calls["n"] == 2


def test_does_not_retry_non_retryable_auth_error(empty_registry):
    gemini = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash")],
                           raise_on_generate=AuthenticationError("bad key", provider="gemini"))
    empty_registry.register("gemini", lambda: gemini)
    gateway = ModelGateway(registry=empty_registry, router=ModelRouter(empty_registry),
                            retry_policy=RetryPolicy(max_attempts=3, backoff_base_s=0.001))

    try:
        gateway.generate(_simple_request(), fallback_policy=FallbackPolicy(fallbacks=[]))
        assert False, "expected AuthenticationError"
    except AuthenticationError:
        pass
    assert len(gemini.generate_calls) == 1  # no retry attempted


def test_falls_back_to_secondary_provider_on_unavailable(empty_registry):
    primary = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash")],
                            raise_on_generate=ModelUnavailableError("down", provider="gemini"))
    secondary = FakeProvider("ollama", [make_model("ollama", "llama3.2")], response_text="from ollama")
    empty_registry.register("gemini", lambda: primary)
    empty_registry.register("ollama", lambda: secondary)
    gateway = ModelGateway(registry=empty_registry, router=ModelRouter(empty_registry),
                            retry_policy=RetryPolicy(max_attempts=1))

    response = gateway.generate(
        _simple_request(),
        provider_id="gemini", model_id="gemini-2.5-flash",
        fallback_policy=FallbackPolicy(fallbacks=[("ollama", "llama3.2")]),
    )
    assert response.content == "from ollama"
    assert response.provider == "ollama"


def test_no_fallback_configured_raises_original_error(empty_registry):
    gemini = FakeProvider("gemini", [make_model("gemini", "gemini-2.5-flash")],
                           raise_on_generate=ModelUnavailableError("down", provider="gemini"))
    empty_registry.register("gemini", lambda: gemini)
    gateway = ModelGateway(registry=empty_registry, router=ModelRouter(empty_registry),
                            retry_policy=RetryPolicy(max_attempts=1))

    try:
        gateway.generate(_simple_request(), fallback_policy=FallbackPolicy(fallbacks=[]))
        assert False, "expected ModelUnavailableError"
    except ModelUnavailableError:
        pass
