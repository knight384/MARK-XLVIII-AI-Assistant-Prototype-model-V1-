"""
core.llm.errors — provider-neutral error taxonomy.

Provider-specific exceptions (google.genai errors, requests.exceptions, etc.)
are translated into these types at the adapter boundary (Part 22, Phase 2
spec), so the Gateway/Router/callers only ever need to handle one hierarchy
regardless of which provider raised the underlying error.
"""
from __future__ import annotations


class ModelError(Exception):
    """Base class for all Model Gateway errors."""
    retryable: bool = False

    def __init__(self, message: str, *, provider: str | None = None,
                 model: str | None = None, cause: Exception | None = None):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.cause = cause


class ProviderError(ModelError):
    """Generic provider-side failure that doesn't fit a more specific type."""


class AuthenticationError(ModelError):
    """Invalid/missing credentials. NOT retryable — retrying won't help."""
    retryable = False


class RateLimitError(ModelError):
    """Provider rate limit hit. Retryable with backoff."""
    retryable = True


class TimeoutError(ModelError):  # noqa: A001 - intentionally shadows builtin within this module's namespace
    """Request exceeded its timeout. Retryable."""
    retryable = True


class ConnectionError(ModelError):  # noqa: A001
    """Network/connection failure reaching the provider. Retryable."""
    retryable = True


class CapabilityError(ModelError):
    """Requested capability (vision, tool_calling, etc.) is not supported by
    the selected provider/model. NOT retryable — a different model is needed,
    not another attempt at the same one."""
    retryable = False


class ConfigurationError(ModelError):
    """Provider/model misconfigured (bad base_url, missing required setting).
    NOT retryable."""
    retryable = False


class ModelUnavailableError(ModelError):
    """The requested provider/model is not currently available (health check
    failed, model not pulled locally, etc). Retryable at the Router level via
    fallback, but not by simply retrying the same provider."""
    retryable = False
