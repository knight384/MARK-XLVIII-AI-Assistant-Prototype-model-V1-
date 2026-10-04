"""tests/llm/test_gemini_provider.py — Gemini adapter tests with a mocked SDK."""
from __future__ import annotations

import sys
import types as pytypes
from unittest.mock import MagicMock

import pytest

from core.llm.errors import AuthenticationError, CapabilityError
from core.llm.providers.gemini import GeminiProvider
from core.llm.types import Message, ModelRequest


def _install_fake_genai(monkeypatch, generate_content_impl):
    """Installs a fake `google.genai` module into sys.modules so
    `from google import genai` inside the adapter picks it up, without
    needing the real google-genai package installed or any network access."""
    fake_google = pytypes.ModuleType("google")
    fake_genai = pytypes.ModuleType("google.genai")

    class FakeModels:
        def generate_content(self, model, contents, config=None):
            return generate_content_impl(model, contents, config)

    class FakeClient:
        def __init__(self, api_key):
            self.api_key = api_key
            self.models = FakeModels()

    fake_genai.Client = FakeClient
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)


def test_generate_returns_text(monkeypatch):
    def impl(model, contents, config):
        resp = MagicMock()
        resp.text = "hello from gemini"
        return resp

    _install_fake_genai(monkeypatch, impl)
    provider = GeminiProvider(api_key_getter=lambda: "fake-key")
    response = provider.generate(ModelRequest(messages=[Message(role="user", content="hi")]),
                                  model_id="gemini-2.5-flash")
    assert response.content == "hello from gemini"
    assert response.provider == "gemini"


def test_missing_api_key_raises_authentication_error():
    def broken_key():
        raise RuntimeError("Gemini API key not configured.")

    provider = GeminiProvider(api_key_getter=broken_key)
    with pytest.raises(AuthenticationError):
        provider.generate(ModelRequest(messages=[Message(role="user", content="hi")]),
                           model_id="gemini-2.5-flash")


def test_tool_calling_on_unknown_model_raises_capability_error(monkeypatch):
    _install_fake_genai(monkeypatch, lambda *a, **k: MagicMock(text=""))
    provider = GeminiProvider(api_key_getter=lambda: "fake-key")
    request = ModelRequest(
        messages=[Message(role="user", content="hi")],
        tools=[{"name": "some_tool", "parameters": {}}],
    )
    with pytest.raises(CapabilityError):
        provider.generate(request, model_id="not-a-real-model")


def test_health_check_reports_unconfigured():
    def broken_key():
        raise RuntimeError("no key")
    provider = GeminiProvider(api_key_getter=broken_key)
    status = provider.health_check()
    assert status.healthy is False


def test_health_check_reports_configured():
    provider = GeminiProvider(api_key_getter=lambda: "fake-key")
    status = provider.health_check()
    assert status.healthy is True
