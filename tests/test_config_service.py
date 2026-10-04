"""tests/test_config_service.py"""
import json

import pytest

from core.config.service import ConfigService, get_config_service


def test_singleton_identity():
    a = get_config_service()
    b = get_config_service()
    assert a is b


def test_load_non_secret_config(isolated_config: ConfigService):
    isolated_config.set("os_system", "linux")
    assert isolated_config.get("os_system") == "linux"
    # Persisted to app_config.json, not the legacy file.
    assert isolated_config.app_config_path.exists()
    data = json.loads(isolated_config.app_config_path.read_text())
    assert data["os_system"] == "linux"


def test_get_missing_key_returns_default(isolated_config: ConfigService):
    assert isolated_config.get("does_not_exist", "fallback") == "fallback"


def test_get_rejects_secret_keys(isolated_config: ConfigService):
    with pytest.raises(ValueError):
        isolated_config.get("gemini_api_key")
    with pytest.raises(ValueError):
        isolated_config.set("gemini_api_key", "sk-whatever")


def test_secret_round_trip_through_config_service(isolated_config: ConfigService):
    isolated_config.set_secret("gemini_api_key", "test-key-12345")
    assert isolated_config.get_secret("gemini_api_key") == "test-key-12345"
    assert isolated_config.get_gemini_api_key() == "test-key-12345"


def test_get_gemini_api_key_raises_when_unset(isolated_config: ConfigService):
    with pytest.raises(RuntimeError):
        isolated_config.get_gemini_api_key()


def test_secret_is_never_written_to_app_config_json(isolated_config: ConfigService):
    isolated_config.set_secret("gemini_api_key", "super-secret-value")
    isolated_config.set("stt_engine", "whisper")  # trigger a config file write
    if isolated_config.app_config_path.exists():
        contents = isolated_config.app_config_path.read_text()
        assert "super-secret-value" not in contents


def test_legacy_migration_imports_secret_and_settings(tmp_path, monkeypatch):
    """Simulates a Phase-0-era config/api_keys.json and confirms Phase 1
    migrates its secret + settings into the new stores without deleting it."""
    monkeypatch.setattr("core.config.service._get_base_dir", lambda: tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    legacy_path = config_dir / "api_keys.json"
    legacy_path.write_text(json.dumps({
        "gemini_api_key": "legacy-key-abc",
        "os_system": "windows",
        "stt_engine": "vosk",
    }))

    ConfigService._instance = None
    svc = ConfigService()

    assert svc.get_secret("gemini_api_key") == "legacy-key-abc"
    assert svc.get("os_system") == "windows"
    assert svc.get("stt_engine") == "vosk"
    # Legacy file must be left in place, not deleted.
    assert legacy_path.exists()
    assert svc.migration_note is not None


def test_is_configured_reflects_secret_and_os(isolated_config: ConfigService):
    assert isolated_config.is_configured() is False
    isolated_config.set_secret("gemini_api_key", "k")
    isolated_config.set("os_system", "linux")
    assert isolated_config.is_configured() is True
