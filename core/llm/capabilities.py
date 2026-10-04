"""
core.llm.capabilities — machine-readable capability declarations.

The Router uses these flags to decide which provider/model can actually
serve a given request (Phase 2 spec, Part 5). A provider/model may support
some capabilities and not others — nothing here assumes uniformity.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapabilities:
    text_generation: bool = False
    vision: bool = False
    tool_calling: bool = False
    structured_output: bool = False
    streaming: bool = False
    embeddings: bool = False
    reasoning: bool = False
    realtime_audio_session: bool = False
    local_execution: bool = False

    def supports(self, *required: str) -> bool:
        """True if every named capability is set on this instance."""
        return all(getattr(self, name, False) for name in required)

    def missing(self, *required: str) -> list[str]:
        return [name for name in required if not getattr(self, name, False)]
