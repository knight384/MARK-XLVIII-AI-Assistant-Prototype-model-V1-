"""tests/test_startup_smoke.py

A minimal characterization test standing in for a full application startup
(PyQt6/google-genai/sounddevice are not assumed to be installed in every
environment this suite runs in). This exercises the same sequence Phase 1's
acceptance criteria describe:

    Configuration loaded -> Logging initialized -> Gemini credential loads
    through the new config path -> Dashboard configuration available

without actually opening an audio device, a Gemini Live session, or a
network port.
"""
from core.config.service import ConfigService
from core.logging_setup import configure_logging, is_configured as logging_is_configured


def test_full_startup_sequence(isolated_config: ConfigService, tmp_path):
    # 1. Configuration loads (isolated_config fixture already did this).
    assert isinstance(isolated_config, ConfigService)

    # 2. Logging initializes without raising.
    import core.logging_setup as ls
    ls._configured = False
    configure_logging(log_dir=tmp_path)
    assert logging_is_configured() is True
    ls._configured = False

    # 3. Simulate a completed first-run setup, then confirm the Gemini
    #    credential loads through ConfigService exactly as main.py's
    #    _get_api_key() does post-Phase-1.
    isolated_config.set_secret("gemini_api_key", "AIzaFakeKeyForTestingOnly")
    isolated_config.set("os_system", "linux")
    assert isolated_config.is_configured() is True
    assert isolated_config.get_gemini_api_key() == "AIzaFakeKeyForTestingOnly"

    # 4. Dashboard configuration is available (typed view, doesn't require
    #    fastapi/uvicorn to be installed just to read config).
    dash = isolated_config.dashboard()
    assert dash.port == 8000
    assert dash.cert_file.name == "jarvis.crt"
    assert dash.key_file.name == "jarvis.key"
    assert dash.tls_available is False  # no cert generated in this test


def test_missing_credential_is_reported_not_silently_swallowed(isolated_config: ConfigService):
    assert isolated_config.is_configured() is False
    try:
        isolated_config.get_gemini_api_key()
        assert False, "expected RuntimeError for missing credential"
    except RuntimeError as exc:
        assert "Gemini API key" in str(exc)
