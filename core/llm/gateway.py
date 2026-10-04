"""
core.llm.gateway — the Model Gateway (Phase 2 spec, Part 4/Part 20-21).

Applications/agents call `ModelGateway.generate(...)` (or the module-level
convenience `generate_text(...)`) instead of constructing provider clients
directly. The Gateway:
  1. asks the Router for a (provider, model) decision,
  2. calls that provider's `generate()`,
  3. on a retryable error, retries per RetryPolicy,
  4. on ModelUnavailableError or retry exhaustion, tries the next entry in
     FallbackPolicy (if configured),
  5. raises the final ModelError if nothing worked.

Gemini Live is NOT routed through this Gateway — see providers/gemini_live.py.
"""
from __future__ import annotations

import logging
import time

from .errors import ModelError, ModelUnavailableError
from .policies import FallbackPolicy, RetryPolicy
from .registry import ProviderRegistry, get_default_registry
from .router import ModelRouter, NoCompatibleModelError, RoutingDecision
from .tiers import ModelTier
from .types import Message, ModelRequest, ModelResponse

logger = logging.getLogger(__name__)


class ModelGateway:
    def __init__(self, registry: ProviderRegistry | None = None, router: ModelRouter | None = None,
                 retry_policy: RetryPolicy | None = None):
        self._registry = registry or get_default_registry()
        self._router = router or ModelRouter(self._registry)
        self._retry_policy = retry_policy or RetryPolicy()

    def generate(
        self,
        request: ModelRequest,
        *,
        task_type: str | ModelTier = "default",
        required_capabilities: tuple[str, ...] = (),
        privacy: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        fallback_policy: FallbackPolicy | None = None,
    ) -> ModelResponse:
        decision = self._router.route(
            task_type=task_type, required_capabilities=required_capabilities,
            privacy=privacy, override_provider=provider_id, override_model=model_id,
        )
        try:
            return self._generate_with_retry(request, decision)
        except ModelError as exc:
            fallback_policy = fallback_policy or FallbackPolicy(
                fallbacks=[(p, m) for p, m in [("ollama", None), ("gemini", "gemini-2.5-flash")]
                           if p != decision.provider_id]
            )
            for fb_provider, fb_model in fallback_policy.fallbacks:
                try:
                    fb_decision = self._router.route(override_provider=fb_provider, override_model=fb_model)
                except NoCompatibleModelError:
                    continue
                logger.warning(
                    "Provider '%s' failed (%s) — falling back to '%s'/'%s'.",
                    decision.provider_id, type(exc).__name__, fb_decision.provider_id, fb_decision.model_id,
                )
                try:
                    return self._generate_with_retry(request, fb_decision)
                except ModelError:
                    continue
            raise

    def _generate_with_retry(self, request: ModelRequest, decision: RoutingDecision) -> ModelResponse:
        provider = self._registry.get(decision.provider_id)
        if provider is None:
            raise ModelUnavailableError(f"Provider '{decision.provider_id}' could not be constructed.",
                                         provider=decision.provider_id, model=decision.model_id)
        attempt = 0
        last_error: ModelError | None = None
        while True:
            attempt += 1
            try:
                return provider.generate(request, decision.model_id)
            except ModelError as exc:
                last_error = exc
                if not self._retry_policy.should_retry(exc, attempt):
                    raise
                delay = self._retry_policy.backoff_seconds(attempt)
                logger.info("Retrying %s/%s after %.2fs (attempt %d): %s",
                            decision.provider_id, decision.model_id, delay, attempt, exc)
                time.sleep(delay)

    def health_check_all(self):
        return self._registry.health_check_all()


_default_gateway: ModelGateway | None = None


def get_default_gateway() -> ModelGateway:
    global _default_gateway
    if _default_gateway is None:
        _default_gateway = ModelGateway()
    return _default_gateway


def generate_text(
    prompt: str,
    *,
    system: str | None = None,
    task_type: str | ModelTier = "default",
    tools: list[dict] | None = None,
) -> str:
    """Convenience wrapper for the common case used throughout actions/*.py:
    'send one prompt, get text back.' Centralizes what used to be duplicated
    genai.Client construction + generate_content() calls across ~10 modules
    (Phase 2 spec, Part 36: 'The same API handling must not be implemented
    separately' across those files)."""
    gateway = get_default_gateway()
    request = ModelRequest(
        messages=[Message(role="user", content=prompt)],
        system_instruction=system,
        tools=tools,
    )
    response = gateway.generate(request, task_type=task_type)
    return response.content
