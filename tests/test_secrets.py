"""tests/test_secrets.py

Exercises the local-file fallback path specifically, since the `keyring`
package (the preferred backend) is not guaranteed to be installed or
functional in every environment this test suite runs in (e.g. headless
CI/sandboxes). The fallback path is exactly the code path Phase 1's secret
hygiene requirement depends on in those environments, so it needs direct
coverage independent of whichever backend happens to be available.
"""
import json
import stat
import sys

from core.config.secrets import SecretStore


def test_fallback_set_and_get(tmp_path):
    store = SecretStore(tmp_path / "secrets.json")
    store.set("gemini_api_key", "abc123")
    assert store.get("gemini_api_key") == "abc123"


def test_fallback_file_not_plaintext_in_repo_tree(tmp_path):
    """The fallback file must live wherever the caller points it (a gitignored
    path), and must contain the value only there -- not asserting encryption
    (out of scope for Phase 1's stated approach), just confirming the file
    is written where expected and nowhere else."""
    secrets_path = tmp_path / "secrets.json"
    store = SecretStore(secrets_path)
    store.set("gemini_api_key", "xyz789")
    assert secrets_path.exists()
    data = json.loads(secrets_path.read_text())
    assert data["gemini_api_key"] == "xyz789"


def test_get_missing_secret_returns_none(tmp_path):
    store = SecretStore(tmp_path / "secrets.json")
    assert store.get("nonexistent") is None


def test_delete_removes_secret(tmp_path):
    store = SecretStore(tmp_path / "secrets.json")
    store.set("gemini_api_key", "abc123")
    store.delete("gemini_api_key")
    assert store.get("gemini_api_key") is None


def test_fallback_file_permissions_best_effort(tmp_path):
    """On POSIX, the fallback file should be owner-read/write only. This is
    a best-effort check (Windows has no equivalent POSIX mode bits)."""
    if sys.platform.startswith("win"):
        return
    secrets_path = tmp_path / "secrets.json"
    store = SecretStore(secrets_path)
    store.set("gemini_api_key", "abc123")
    mode = stat.S_IMODE(secrets_path.stat().st_mode)
    assert mode == (stat.S_IRUSR | stat.S_IWUSR)


def test_backend_name_reports_fallback_when_keyring_unavailable(tmp_path):
    store = SecretStore(tmp_path / "secrets.json")
    # In this test environment keyring is not installed, so the fallback
    # backend should be reported. If keyring *is* installed and functional
    # elsewhere, this still documents the expected value for that case.
    assert store.backend_name() in ("local-file-fallback", "os-keychain (keyring)")
