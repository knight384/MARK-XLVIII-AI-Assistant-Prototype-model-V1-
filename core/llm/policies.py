"""
core.llm.policies — provider-neutral retry/timeout/fallback policies
(Phase 2 spec, Part 21).

Realtime sessions (Gemini Live) do NOT use RetryPolicy — retrying a session
connect by re-entering the Gateway could create multiple concurrent Live
sessions, which is explicitly forbidden by the spec (Part 21: "Do not let a
retry policy accidentally create multiple Gemini Live sessions."). Session
lifecycle/reconnect is handled entirely inside RealtimeModelSession instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .errors import ModelError


@dataclass(frozen=True)
class TimeoutPolicy:
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 60.0


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2          # total attempts including the first, e.g. 2 = one retry
    backoff_base_s: float = 0.5
    backoff_multiplier: float = 2.0

    def should_retry(self, error: Exception, attempt: int) -> bool:
        if attempt >= self.max_attempts:
            return False
        if isinstance(error, ModelError):
            return error.retryable
        # Unknown/unclassified errors: don't retry by default — safer than
        # silently retrying something like a malformed-request bug.
        return False

    def backoff_seconds(self, attempt: int) -> float:
        return self.backoff_base_s * (self.backoff_multiplier ** max(0, attempt - 1))


@dataclass(frozen=True)
class FallbackPolicy:
    """An ordered list of (provider_id, model_id) pairs to try after the
    primary choice, used by the Gateway when the primary raises a
    ModelUnavailableError or exhausts its RetryPolicy on a retryable error."""
    fallbacks: list[tuple[str, str]] = field(default_factory=list)
