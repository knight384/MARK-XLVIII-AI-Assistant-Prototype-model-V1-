"""
core.config — the application's single configuration path (Phase 1).

Usage:
    from core.config import get_config_service
    config = get_config_service()
    api_key = config.get_gemini_api_key()
    os_name = config.get("os_system", "windows")
"""
from .service import ConfigService, get_config_service
from .models import DashboardConfig, EngineConfig, PathsConfig

__all__ = [
    "ConfigService",
    "get_config_service",
    "DashboardConfig",
    "EngineConfig",
    "PathsConfig",
]
