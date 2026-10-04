"""tests/llm/test_openai_compatible_provider.py — mocked HTTP tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from core.llm.errors import AuthenticationError, RateLimitError
from core.llm.providers.openai_compatible import OpenAICompatibleProvider
from core.llm.types import Message, ModelRequest


def _provider():
    return OpenAICompatibleProvider(
        base_url_getter=lambda: "http://localhost:1234",
        model_getter=lambda: "local-model",
    )


def test_generate_success():
    provider = _provider()
    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "choices": [{"message": {"content": "hi from lm studio"}, "finish_reason": "stop"}]
    }
    fake_resp.raise_for_status = MagicMock()
    with patch("core.llm.providers.openai_compatible.requests.post", return_value=fake_resp):
        response = provider.generate(
            ModelRequest(messages=[Message(role="user", content="hello")]), "local-model"
        )
    assert response.content == "hi from lm studio"
    assert response.finish_reason == "stop"


def test_generate_401_raises_authentication_error():
    provider = _provider()
    fake_resp = MagicMock()
    fake_resp.status_code = 401
    fake_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=fake_resp)
    with patch("core.llm.providers.openai_compatible.requests.post", return_value=fake_resp):
        with pytest.raises(AuthenticationError):
            provider.generate(ModelRequest(messages=[Message(role="user", content="hi")]), "local-model")


def test_generate_429_raises_rate_limit_error():
    provider = _provider()
    fake_resp = MagicMock()
    fake_resp.status_code = 429
    fake_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=fake_resp)
    with patch("core.llm.providers.openai_compatible.requests.post", return_value=fake_resp):
        with pytest.raises(RateLimitError):
            provider.generate(ModelRequest(messages=[Message(role="user", content="hi")]), "local-model")


def test_tool_calls_parsed():
    provider = _provider()
    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "get_weather", "arguments": '{"city": "SF"}'}}],
            },
            "finish_reason": "tool_calls",
        }]
    }
    fake_resp.raise_for_status = MagicMock()
    with patch("core.llm.providers.openai_compatible.requests.post", return_value=fake_resp):
        response = provider.generate(
            ModelRequest(messages=[Message(role="user", content="weather?")], tools=[{"name": "get_weather"}]),
            "local-model",
        )
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "get_weather"
    assert response.tool_calls[0].arguments == {"city": "SF"}


def test_health_check_unconfigured():
    provider = OpenAICompatibleProvider(base_url_getter=lambda: "", model_getter=lambda: "x")
    status = provider.health_check()
    assert status.healthy is False
