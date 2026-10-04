"""
core.config.service — the single application-level configuration path.

Phase 0 found THREE overlapping ways this app read configuration:
  - config/__init__.py            (OS detection only)
  - memory/config_manager.py      (api key persistence, despite living
                                    under memory/)
  - ad hoc `json.load(open(".../config/api_keys.json"))` repeated in
    main.py, ui.py, dashboard/server.py, core/llm_client.py, and every
    actions/*.py module that calls Gemini directly (15+ call sites)

This module replaces all of that with one `ConfigService`, obtained via
`get_config_service()`. It is intentionally the *only* thing in the codebase
that touches config/app_config.json, config/secrets.json, or the legacy
config/api_keys.json directly.

Non-secret settings (os_system, stt_engine, tts_engine, llm_provider, etc.)
live in config/app_config.json.
Secrets (currently: gemini_api_key) live behind `core.config.secrets.SecretStore`
(OS keychain, with a local-file fallback that is gitignored) — never in
app_config.json, never committed.

Legacy migration: if config/api_keys.json exists (Phase 0-era combined file),
its non-secret keys are copied into app_config.json and its secret key(s)
into the SecretStore, on first read, without deleting the user's original
file (so nothing is silently destroyed if migration is interrupted). Once
both new stores are functioning, the legacy file is no longer read again.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from .models import DashboardConfig, EngineConfig, PathsConfig
from .secrets import SecretStore

logger = logging.getLogger(__name__)

# Keys that must NEVER live in app_config.json — they belong in the SecretStore.
_SECRET_KEYS = frozenset({"gemini_api_key", "openai_api_key", "anthropic_api_key"})


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # core/config/service.py -> core/config -> core -> <project root>
    return Path(__file__).resolve().parent.parent.parent


class ConfigService:
    """Process-wide configuration singleton. Thread-safe for the simple
    read/write patterns used by this app (small JSON files, infrequent
    writes from the setup wizard / settings UI)."""

    _instance: "ConfigService | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "ConfigService":
        with cls._instance_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._init()
                cls._instance = inst
            return cls._instance

    # -- initialization ---------------------------------------------------

    def _init(self) -> None:
        self._data_lock = threading.Lock()
        self.base_dir = _get_base_dir()
        self.config_dir = self.base_dir / "config"
        self.certs_dir = self.config_dir / "certs"
        self.memory_dir = self.base_dir / "memory"

        self.app_config_path = self.config_dir / "app_config.json"
        self.legacy_config_path = self.config_dir / "api_keys.json"
        self.secrets_fallback_path = self.config_dir / "secrets.json"

        self._secret_store = SecretStore(self.secrets_fallback_path)
        self._data: dict[str, Any] = {}
        self.migration_note: Optional[str] = None

        self.reload()

    def reload(self) -> None:
        """(Re)load non-secret config from disk, migrating the legacy
        combined file on first encounter."""
        with self._data_lock:
            data: dict[str, Any] = {}
            if self.app_config_path.exists():
                try:
                    data = json.loads(self.app_config_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    logger.error(
                        "Failed to parse %s (%s) — starting from an empty config.",
                        self.app_config_path, type(exc).__name__,
                    )
                    data = {}

            if self.legacy_config_path.exists():
                self._migrate_legacy_locked(data)

            self._data = data

    def _migrate_legacy_locked(self, data: dict[str, Any]) -> None:
        """Import config/api_keys.json (Phase 0-era file) into the new
        stores. Never deletes the legacy file — migration is additive and
        idempotent, and failures are reported rather than silently eaten."""
        try:
            legacy = json.loads(self.legacy_config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.migration_note = (
                f"Legacy config file {self.legacy_config_path} exists but could not "
                f"be parsed ({type(exc).__name__}); it was left untouched and ignored."
            )
            logger.warning(self.migration_note)
            return

        migrated_secret_keys: list[str] = []
        migrated_config_keys: list[str] = []

        for key, value in legacy.items():
            if key in _SECRET_KEYS:
                if value and not self._secret_store.get(key):
                    self._secret_store.set(key, str(value))
                    migrated_secret_keys.append(key)
            else:
                if key not in data:
                    data[key] = value
                    migrated_config_keys.append(key)

        if migrated_secret_keys or migrated_config_keys:
            self._save_app_config_locked(data)
            self.migration_note = (
                f"Migrated legacy config from {self.legacy_config_path.name}: "
                f"secrets={migrated_secret_keys or 'none'}, "
                f"settings={migrated_config_keys or 'none'}. "
                f"Original file was left in place; it is now ignored by git "
                f"and no longer read after this migration."
            )
            logger.info(self.migration_note)

    def _save_app_config_locked(self, data: dict[str, Any]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.app_config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # -- generic config get/set -------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        if key in _SECRET_KEYS:
            raise ValueError(f"'{key}' is a secret — use get_secret() instead.")
        with self._data_lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key in _SECRET_KEYS:
            raise ValueError(f"'{key}' is a secret — use set_secret() instead.")
        with self._data_lock:
            self._data[key] = value
            self._save_app_config_locked(self._data)

    def is_configured(self) -> bool:
        """Mirrors the app's existing 'has the user completed setup?' check
        (previously: presence of gemini_api_key + os_system in api_keys.json)."""
        return bool(self.get_secret("gemini_api_key")) and bool(self.get("os_system"))

    # -- secrets ------------------------------------------------------------

    def get_secret(self, name: str) -> Optional[str]:
        return self._secret_store.get(name)

    def set_secret(self, name: str, value: str) -> None:
        self._secret_store.set(name, value)

    def secret_backend(self) -> str:
        return self._secret_store.backend_name()

    # -- convenience: Gemini API key (the one secret every call site needs) -

    def get_gemini_api_key(self) -> str:
        key = self.get_secret("gemini_api_key")
        if not key:
            raise RuntimeError(
                "Gemini API key not configured. Complete first-run setup, or set it via "
                "ConfigService().set_secret('gemini_api_key', '<key>')."
            )
        return key

    # -- typed views ----------------------------------------------------

    def paths(self) -> PathsConfig:
        return PathsConfig(
            base_dir=self.base_dir,
            config_dir=self.config_dir,
            certs_dir=self.certs_dir,
            memory_dir=self.memory_dir,
        )

    def dashboard(self, port: int = 8000) -> DashboardConfig:
        return DashboardConfig(
            port=self.get("dashboard_port", port),
            certs_dir=self.certs_dir,
            cert_file=self.certs_dir / "jarvis.crt",
            key_file=self.certs_dir / "jarvis.key",
        )

    def engines(self) -> EngineConfig:
        return EngineConfig(
            stt_engine=self.get("stt_engine", "whisper"),
            tts_engine=self.get("tts_engine", "edgetts"),
            llm_provider=self.get("llm_provider", "ollama"),
            llm_url=self.get("llm_url", "http://localhost:11434"),
            llm_model=self.get("llm_model", "llama3.2"),
            os_system=self.get("os_system", "windows"),
        )


def get_config_service() -> ConfigService:
    """Application-wide entry point. Prefer this over instantiating
    ConfigService() directly, so intent is explicit at call sites."""
    return ConfigService()
