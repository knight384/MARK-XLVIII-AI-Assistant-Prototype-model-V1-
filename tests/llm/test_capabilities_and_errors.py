"""tests/llm/test_capabilities_and_errors.py"""
from __future__ import annotations

from core.llm.capabilities import ModelCapabilities
from core.llm.errors import (
    AuthenticationError, CapabilityError, ConnectionError as LLMConnectionError,
    ModelUnavailableError, RateLimitError, TimeoutError as LLMTimeoutError,
)


def test_supports_all_true():
    caps = ModelCapabilities(text_generation=True, vision=True, tool_calling=True)
    assert caps.supports("vision", "tool_calling") is True


def test_supports_false_if_any_missing():
    caps = ModelCapabilities(text_generation=True, vision=False)
    assert caps.supports("vision") is False


def test_missing_lists_unmet_capabilities():
    caps = ModelCapabilities(text_generation=True, vision=False, tool_calling=True)
    assert caps.missing("vision", "tool_calling", "streaming") == ["vision", "streaming"]


def test_retryable_flags():
    assert RateLimitError("x").retryable is True
    assert LLMTimeoutError("x").retryable is True
    assert LLMConnectionError("x").retryable is True
    assert AuthenticationError("x").retryable is False
    assert CapabilityError("x").retryable is False
    assert ModelUnavailableError("x").retryable is False
