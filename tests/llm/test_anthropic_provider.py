"""tests/llm/test_anthropic_provider.py — confirms the skeleton doesn't fake functionality."""
from __future__ import annotations

import pytest

from core.llm.providers.anthropic import AnthropicProvider


def test_is_configured_is_false():
    provider = AnthropicProvider()
    assert provider.is_configured() is False


def test_health_check_reports_unavailable():
    provider = AnthropicProvider()
    status = provider.health_check()
    assert status.healthy is False
    assert "not implemented" in status.detail.lower()


def test_generate_raises_not_implemented():
    provider = AnthropicProvider()
    with pytest.raises(NotImplementedError):
        provider.generate(None, model_id="claude-sonnet-4-6")


def test_list_models_reports_unavailable_availability():
    provider = AnthropicProvider()
    models = provider.list_models()
    assert len(models) == 1
    assert models[0].availability == "unavailable"
