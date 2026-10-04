"""tests/llm/test_ollama_provider.py — Ollama adapter tests with mocked HTTP."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from core.llm.errors import ConnectionError as LLMConnectionError, ModelUnavailableError
from core.llm.providers.ollama import OllamaProvider
from core.llm.types import Message, ModelRequest


def _provider():
    return OllamaProvider(
        base_url_getter=lambda: "http://localhost:11434",
        model_getter=lambda: "llama3.2",
    )


def test_generate_success():
    provider = _provider()
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"message": {"content": "hi from ollama"}}
    fake_resp.raise_for_status = MagicMock()
    with patch("core.llm.providers.ollama.requests.post", return_value=fake_resp) as post:
        response = provider.generate(
            ModelRequest(messages=[Message(role="user", content="hello")]), "llama3.2"
        )
    assert response.content == "hi from ollama"
    assert post.call_args.kwargs["json"]["model"] == "llama3.2"


def test_generate_connection_error_translated():
    provider = _provider()
    with patch("core.llm.providers.ollama.requests.post",
               side_effect=requests.exceptions.ConnectionError("refused")):
        with pytest.raises(LLMConnectionError):
            provider.generate(ModelRequest(messages=[Message(role="user", content="hi")]), "llama3.2")


def test_generate_404_raises_model_unavailable():
    provider = _provider()
    fake_resp = MagicMock()
    fake_resp.status_code = 404
    fake_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=fake_resp)
    with patch("core.llm.providers.ollama.requests.post", return_value=fake_resp):
        with pytest.raises(ModelUnavailableError):
            provider.generate(ModelRequest(messages=[Message(role="user", content="hi")]), "nonexistent-model")


def test_health_check_unreachable():
    provider = _provider()
    with patch("core.llm.providers.ollama.requests.get",
               side_effect=requests.exceptions.ConnectionError("refused")):
        status = provider.health_check()
    assert status.healthy is False


def test_health_check_reachable_model_available():
    provider = _provider()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"models": [{"name": "llama3.2:latest"}]}
    with patch("core.llm.providers.ollama.requests.get", return_value=fake_resp):
        status = provider.health_check()
    assert status.healthy is True


def test_health_check_reachable_model_missing():
    provider = _provider()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"models": [{"name": "mistral:latest"}]}
    with patch("core.llm.providers.ollama.requests.get", return_value=fake_resp):
        status = provider.health_check()
    assert status.healthy is True  # server up
    assert "not pulled" in status.detail


def test_no_base_url_configured():
    provider = OllamaProvider(base_url_getter=lambda: "", model_getter=lambda: "llama3.2")
    status = provider.health_check()
    assert status.healthy is False
