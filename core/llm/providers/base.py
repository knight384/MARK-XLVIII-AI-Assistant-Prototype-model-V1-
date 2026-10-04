"""
core.llm.providers.base — the abstract Provider interface (Phase 2 spec, Part 3).

Every adapter (Gemini, Ollama, OpenAI-compatible, OpenAI, Anthropic)
implements this. The Gateway/Router only ever talk to this interface, never
to a provider's native SDK directly (Gemini Live is the one deliberate
exception — see providers/gemini_live.py's module docstring).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..capabilities import ModelCapabilities
from ..types import ModelRequest, ModelResponse, StreamEvent


@dataclass(frozen=True)
class ModelInfo:
    """Metadata for one model exposed by a provider (Phase 2 spec, Part 4)."""
    model_id: str
    provider_id: str
    display_name: str
    capabilities: ModelCapabilities
    context_window: int | None = None
    cost_profile: str = "unknown"          # "free" | "local" | "low" | "medium" | "high" | "unknown"
    local_or_cloud: str = "cloud"          # "local" | "cloud"
    availability: str = "unknown"          # "available" | "unavailable" | "unknown" (set by health_check)


@dataclass(frozen=True)
class HealthStatus:
    healthy: bool
    detail: str = ""
    checked_models: list[str] = field(default_factory=list)


class Provider(ABC):
    """Abstract provider interface."""

    provider_id: str = "base"
    display_name: str = "Base Provider"

    # -- discovery / metadata --------------------------------------------

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """Return known models for this provider. Implementations should
        avoid network calls here where practical (Part 29: no unnecessary
        model-discovery calls) — static/config-declared lists are fine."""
        raise NotImplementedError

    def get_model(self, model_id: str) -> ModelInfo | None:
        for m in self.list_models():
            if m.model_id == model_id:
                return m
        return None

    # -- health -------------------------------------------------------------

    @abstractmethod
    def health_check(self) -> HealthStatus:
        """Must never raise — an unhealthy/unconfigured provider should be
        reported, not crash the caller (Part 19)."""
        raise NotImplementedError

    # -- generation -----------------------------------------------------

    @abstractmethod
    def generate(self, request: ModelRequest, model_id: str) -> ModelResponse:
        """Stateless, synchronous generation. Raises core.llm.errors.ModelError
        subclasses on failure — never a raw provider-specific exception."""
        raise NotImplementedError

    def stream(self, request: ModelRequest, model_id: str):
        """Optional: providers that support streaming may override this to
        yield StreamEvent objects. Default: not supported."""
        raise NotImplementedError(f"{self.provider_id} does not implement streaming.")

    # -- misc -------------------------------------------------------------

    def is_configured(self) -> bool:
        """Cheap, local-only check (e.g. 'is a config value present') —
        distinct from health_check(), which may involve network I/O."""
        return True
