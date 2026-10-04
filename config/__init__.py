# config/__init__.py
"""
OS-detection helpers.

Phase 1: delegates the underlying config read to core.config.ConfigService
(single source of truth) instead of reading config/api_keys.json directly.
Public function signatures are unchanged so existing callers
(actions/flight_finder.py, actions/game_updater.py, actions/youtube_video.py)
do not need to change.
"""
import platform


def _platform_os() -> str:
    """Auto-detect OS when no config value is set."""
    return {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(
        platform.system(), "linux"
    )


def get_config() -> dict:
    """Retained for backward compatibility. Returns non-secret settings only
    (secrets live in the SecretStore, not here) -- callers of this repo have
    historically only ever used it for 'os_system'."""
    try:
        from core.config import get_config_service
        svc = get_config_service()
        return {"os_system": svc.get("os_system", _platform_os())}
    except Exception:
        return {}


def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    try:
        from core.config import get_config_service
        return get_config_service().get("os_system", _platform_os()).lower()
    except Exception:
        return _platform_os()


def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"
