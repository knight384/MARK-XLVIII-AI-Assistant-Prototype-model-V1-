"""
core.config.models — lightweight, typed views over configuration values that
already exist in today's app (os_system, dashboard port, cert paths, engine
selection). These are deliberately thin: Phase 1 is a hygiene/foundation
pass, not a redesign of configuration semantics, so this module only wraps
values ConfigService already exposes rather than inventing new settings.

Future phases (Model Gateway, Agent Runtime, etc.) will likely add their own
model files under core/config/ or core/llm/ — this file is intentionally
scoped to what exists today.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathsConfig:
    """Well-known directories, resolved once at startup."""
    base_dir: Path
    config_dir: Path
    certs_dir: Path
    memory_dir: Path


@dataclass(frozen=True)
class DashboardConfig:
    """Mirrors dashboard/server.py's existing constants — not a redesign,
    just a typed accessor so callers don't hardcode paths/ports separately."""
    port: int
    certs_dir: Path
    cert_file: Path
    key_file: Path

    @property
    def tls_available(self) -> bool:
        return self.cert_file.exists() and self.key_file.exists()


@dataclass(frozen=True)
class EngineConfig:
    """STT/TTS/LLM engine selection — unchanged semantics from today's
    api_keys.json fields (stt_engine, tts_engine, llm_provider, llm_url,
    llm_model); just exposed as a typed read instead of ad hoc dict.get()."""
    stt_engine: str = "whisper"
    tts_engine: str = "edgetts"
    llm_provider: str = "ollama"
    llm_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2"
    os_system: str = "windows"
