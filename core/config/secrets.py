"""
core.config.secrets — secret storage abstraction.

Phase 1 goal: get the Gemini API key (and any future secret) out of plaintext,
source-controllable JSON, without requiring every call site to know *how*
the secret is actually stored.

Backend priority:
  1. OS keychain / credential manager, via the optional `keyring` package
     (Windows Credential Locker, macOS Keychain, Linux Secret Service / KWallet).
  2. Local JSON file fallback, stored at config/secrets.json — OUTSIDE version
     control (see .gitignore) — created with owner-only permissions where the
     OS supports it (POSIX chmod 0600; best-effort no-op on Windows, which
     uses ACLs instead of POSIX permission bits).

The fallback exists because not every environment has a working OS keychain
backend (headless Linux/CI/some container setups). Using it still satisfies
the Phase 1 requirement that secrets are never committed to source control —
it is strictly better than the previous plaintext-in-repo-tree behavior, and
callers never need to change when a stronger backend becomes available later.
"""
from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import keyring  # type: ignore
    _KEYRING_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when keyring isn't installed
    keyring = None  # type: ignore
    _KEYRING_AVAILABLE = False

_SERVICE_NAME = "jarvis-mark-xlviii"


class SecretStore:
    """Get/set named secrets through the best available backend."""

    def __init__(self, fallback_path: Path):
        self._fallback_path = fallback_path

    # -- public API ----------------------------------------------------

    def get(self, name: str) -> Optional[str]:
        if _KEYRING_AVAILABLE:
            try:
                value = keyring.get_password(_SERVICE_NAME, name)  # type: ignore[union-attr]
                if value:
                    return value
            except Exception as exc:  # keyring backends can raise many exception types
                logger.warning(
                    "Keyring read failed for secret '%s' (%s) — falling back to local secret store.",
                    name, type(exc).__name__,
                )
        return self._read_fallback().get(name)

    def set(self, name: str, value: str) -> None:
        if _KEYRING_AVAILABLE:
            try:
                keyring.set_password(_SERVICE_NAME, name, value)  # type: ignore[union-attr]
                # Keep the fallback file from also holding a stale copy.
                self._delete_fallback_key(name)
                logger.info("Secret '%s' stored via OS keychain.", name)
                return
            except Exception as exc:
                logger.warning(
                    "Keyring write failed for secret '%s' (%s) — using local secret store fallback.",
                    name, type(exc).__name__,
                )
        data = self._read_fallback()
        data[name] = value
        self._write_fallback(data)
        logger.info("Secret '%s' stored via local secret file fallback.", name)

    def delete(self, name: str) -> None:
        if _KEYRING_AVAILABLE:
            try:
                keyring.delete_password(_SERVICE_NAME, name)  # type: ignore[union-attr]
            except Exception:
                pass
        self._delete_fallback_key(name)

    def backend_name(self) -> str:
        return "os-keychain (keyring)" if _KEYRING_AVAILABLE else "local-file-fallback"

    # -- fallback file helpers ------------------------------------------

    def _read_fallback(self) -> dict:
        if not self._fallback_path.exists():
            return {}
        try:
            return json.loads(self._fallback_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(
                "Failed to read local secret store at %s (%s). Treating as empty.",
                self._fallback_path, type(exc).__name__,
            )
            return {}

    def _write_fallback(self, data: dict) -> None:
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        self._fallback_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(self._fallback_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600, POSIX only
        except Exception:
            # Best-effort: Windows uses ACLs, not POSIX mode bits; nothing more to do here.
            pass

    def _delete_fallback_key(self, name: str) -> None:
        data = self._read_fallback()
        if name in data:
            del data[name]
            self._write_fallback(data)
