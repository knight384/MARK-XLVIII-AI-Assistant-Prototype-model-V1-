"""
memory/config_manager.py — DEPRECATED (Phase 1).

This module used to be one of three overlapping places the app read/wrote
`config/api_keys.json` directly (see the Phase 0 audit). No other module in
the current codebase imports it anymore -- the app now uses
`core.config.get_config_service()` everywhere.

This file is kept as a thin backward-compatible shim (delegating to
ConfigService) in case any external script or future module still imports
it by name, rather than deleting it outright and risking a silent breakage.
Prefer `core.config.get_config_service()` directly in new code.
"""
import logging
from typing import Optional

from core.config import get_config_service

logger = logging.getLogger(__name__)


def ensure_config_dir() -> None:
    get_config_service().config_dir.mkdir(parents=True, exist_ok=True)


def config_exists() -> bool:
    # Historically meant "does api_keys.json exist"; now means "is a secret configured".
    return bool(get_config_service().get_secret("gemini_api_key"))


def save_api_keys(gemini_api_key: str) -> None:
    get_config_service().set_secret("gemini_api_key", gemini_api_key.strip())


def load_api_keys() -> dict:
    key = get_config_service().get_secret("gemini_api_key")
    return {"gemini_api_key": key} if key else {}


def get_gemini_key() -> Optional[str]:
    return get_config_service().get_secret("gemini_api_key")


def is_configured() -> bool:
    key = get_gemini_key()
    return bool(key and len(key) > 15)
