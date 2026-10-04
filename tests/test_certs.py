"""tests/test_certs.py"""
from core.config.certs import ensure_self_signed_cert


def test_generates_cert_and_key_when_missing(tmp_path):
    cert_file = tmp_path / "certs" / "jarvis.crt"
    key_file = tmp_path / "certs" / "jarvis.key"

    ok = ensure_self_signed_cert(cert_file, key_file)

    assert ok is True
    assert cert_file.exists()
    assert key_file.exists()
    assert cert_file.read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
    assert key_file.read_bytes().startswith(b"-----BEGIN")


def test_does_not_regenerate_if_already_present(tmp_path):
    cert_file = tmp_path / "certs" / "jarvis.crt"
    key_file = tmp_path / "certs" / "jarvis.key"
    ensure_self_signed_cert(cert_file, key_file)
    first_cert_bytes = cert_file.read_bytes()

    ensure_self_signed_cert(cert_file, key_file)  # second call: should no-op
    assert cert_file.read_bytes() == first_cert_bytes


def test_fails_safe_without_cryptography(tmp_path, monkeypatch):
    """If `cryptography` were unavailable, generation should fail safely
    (return False) rather than crash the app -- mirrors the dashboard's
    existing behavior of falling back to plain HTTP when no cert exists."""
    import builtins
    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "cryptography" or name.startswith("cryptography."):
            raise ImportError("simulated: cryptography not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)
    cert_file = tmp_path / "certs" / "jarvis.crt"
    key_file = tmp_path / "certs" / "jarvis.key"
    ok = ensure_self_signed_cert(cert_file, key_file)
    assert ok is False
    assert not cert_file.exists()
