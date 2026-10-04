"""
tests/sandbox/test_sandbox.py

Docker tests only run if Docker is actually available in this environment
(spec Part 54/70 — never claim sandbox isolation was tested if Docker
could not actually be run). All other tests exercise the host-restricted
fallback and the SandboxManager's selection logic, which don't require
Docker.
"""
from __future__ import annotations

import shutil

import pytest

from core.sandbox.command import HostRestrictedSandbox
from core.sandbox.docker import DockerSandbox
from core.sandbox.errors import SandboxUnavailableError
from core.sandbox.limits import ResourceLimits
from core.sandbox.manager import SandboxManager
from core.sandbox.workspace import SandboxWorkspace
from core.tools.base import CancellationToken
from core.tools.metadata import RiskLevel

DOCKER_AVAILABLE = shutil.which("docker") is not None


# -- workspace ---------------------------------------------------------

def test_workspace_creates_unique_directory(tmp_path):
    ws1 = SandboxWorkspace(base_dir=tmp_path)
    ws2 = SandboxWorkspace(base_dir=tmp_path)
    assert ws1.path != ws2.path
    assert ws1.path.exists()
    ws1.cleanup()
    ws2.cleanup()


def test_workspace_cleanup_removes_directory(tmp_path):
    ws = SandboxWorkspace(base_dir=tmp_path)
    path = ws.path
    ws.cleanup()
    assert not path.exists()


def test_workspace_context_manager_cleans_up(tmp_path):
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        path = ws.path
        assert path.exists()
    assert not path.exists()


def test_workspace_write_and_read_file(tmp_path):
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        ws.write_file("test.txt", "hello")
        assert ws.read_file("test.txt") == "hello"


def test_workspace_path_traversal_blocked(tmp_path):
    """spec Part 28/54: attempt path traversal must be refused."""
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        with pytest.raises(ValueError):
            ws.resolve("../../etc/passwd")


def test_workspace_nested_path_traversal_blocked(tmp_path):
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        with pytest.raises(ValueError):
            ws.resolve("subdir/../../outside.txt")


def test_workspace_legitimate_nested_path_allowed(tmp_path):
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        resolved = ws.resolve("subdir/file.txt")
        assert ws.path in resolved.parents


# -- host-restricted fallback (spec Part 25 — NOT real isolation) -------

def test_host_restricted_reports_not_real_isolation():
    sandbox = HostRestrictedSandbox()
    assert sandbox.is_real_isolation is False


def test_host_restricted_always_available():
    assert HostRestrictedSandbox().is_available() is True


def test_host_restricted_executes_simple_command(tmp_path):
    sandbox = HostRestrictedSandbox()
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        result = sandbox.execute_command(["echo", "hello"], ws, ResourceLimits())
    assert result.success is True
    assert "hello" in result.stdout
    assert result.backend == "host_restricted"


def test_host_restricted_captures_stderr_and_nonzero_exit(tmp_path):
    sandbox = HostRestrictedSandbox()
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        result = sandbox.execute_command(["python3", "-c", "import sys; sys.exit(1)"], ws, ResourceLimits())
    assert result.success is False
    assert result.exit_code == 1


def test_host_restricted_never_uses_shell_true(tmp_path):
    """spec Part 33: never shell=True for generated commands — a shell
    metacharacter passed as a literal argument must not be interpreted."""
    sandbox = HostRestrictedSandbox()
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        result = sandbox.execute_command(["echo", "$(whoami)"], ws, ResourceLimits())
    assert "$(whoami)" in result.stdout


def test_host_restricted_timeout_terminates_process(tmp_path):
    sandbox = HostRestrictedSandbox()
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        result = sandbox.execute_command(
            ["python3", "-c", "import time; time.sleep(30)"], ws,
            ResourceLimits(timeout_seconds=0.5),
        )
    assert result.timed_out is True
    assert result.success is False


def test_host_restricted_cancellation(tmp_path):
    sandbox = HostRestrictedSandbox()
    token = CancellationToken()
    token.cancel()
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        result = sandbox.execute_command(["echo", "should still finish fast"], ws,
                                          ResourceLimits(timeout_seconds=5), cancellation_token=token)
    assert result.backend == "host_restricted"


def test_host_restricted_output_truncated_to_limit(tmp_path):
    sandbox = HostRestrictedSandbox()
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        result = sandbox.execute_command(
            ["python3", "-c", "print('x' * 1000)"], ws,
            ResourceLimits(output_limit_bytes=100),
        )
    assert len(result.stdout) <= 100


def test_host_restricted_environment_stripped(tmp_path):
    """Defense-in-depth: parent process env (which could contain secrets)
    is not inherited wholesale."""
    import os
    sandbox = HostRestrictedSandbox()
    os.environ["JARVIS_TEST_SECRET_MARKER"] = "should-not-leak"
    try:
        with SandboxWorkspace(base_dir=tmp_path) as ws:
            result = sandbox.execute_command(
                ["python3", "-c", "import os; print(os.environ.get('JARVIS_TEST_SECRET_MARKER', 'NOT_PRESENT'))"],
                ws, ResourceLimits(),
            )
        assert "NOT_PRESENT" in result.stdout
    finally:
        del os.environ["JARVIS_TEST_SECRET_MARKER"]


# -- Docker sandbox (metadata / availability only — see conditional block) -

def test_docker_sandbox_reports_real_isolation():
    assert DockerSandbox().is_real_isolation is True


def test_docker_sandbox_unavailable_reports_false_when_no_docker_binary(monkeypatch):
    sandbox = DockerSandbox()
    monkeypatch.setattr(sandbox, "_docker_path", None)
    assert sandbox.is_available() is False


def test_docker_sandbox_execute_fails_gracefully_when_unavailable(monkeypatch, tmp_path):
    sandbox = DockerSandbox()
    monkeypatch.setattr(sandbox, "_docker_path", None)
    with SandboxWorkspace(base_dir=tmp_path) as ws:
        result = sandbox.execute_command(["echo", "x"], ws, ResourceLimits())
    assert result.success is False
    assert "not available" in result.error.lower()


# -- SandboxManager selection logic --------------------------------------

def test_manager_prefers_docker_when_available(monkeypatch):
    manager = SandboxManager()
    monkeypatch.setattr(manager, "docker_available", lambda force_recheck=False: True)
    backend = manager.select_backend(RiskLevel.LOW)
    assert backend.backend_name == "docker"


def test_manager_uses_fallback_for_low_medium_high_when_docker_unavailable(monkeypatch):
    manager = SandboxManager()
    monkeypatch.setattr(manager, "docker_available", lambda force_recheck=False: False)
    for risk in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH):
        backend = manager.select_backend(risk)
        assert backend.backend_name == "host_restricted"


def test_manager_refuses_critical_without_docker(monkeypatch):
    """spec Part 25: 'The system should be able to refuse dangerous
    execution if no safe sandbox is available.'"""
    manager = SandboxManager()
    monkeypatch.setattr(manager, "docker_available", lambda force_recheck=False: False)
    backend = manager.select_backend(RiskLevel.CRITICAL)
    assert backend is None


def test_manager_execute_command_raises_when_nothing_acceptable(monkeypatch):
    manager = SandboxManager()
    monkeypatch.setattr(manager, "docker_available", lambda force_recheck=False: False)
    with pytest.raises(SandboxUnavailableError):
        manager.execute_command(["echo", "x"], risk_level=RiskLevel.CRITICAL)


def test_manager_execute_command_succeeds_with_fallback_for_medium(monkeypatch, tmp_path):
    manager = SandboxManager()
    monkeypatch.setattr(manager, "docker_available", lambda force_recheck=False: False)
    result = manager.execute_command(["echo", "hi"], risk_level=RiskLevel.MEDIUM,
                                      base_workspace_dir=tmp_path)
    assert result.success is True


def test_manager_probe_result_is_cached(monkeypatch):
    manager = SandboxManager()
    calls = {"n": 0}

    def fake_is_available():
        calls["n"] += 1
        return False

    monkeypatch.setattr(manager._docker, "is_available", fake_is_available)
    manager.docker_available()
    manager.docker_available()
    manager.docker_available()
    assert calls["n"] == 1


def test_manager_force_recheck_bypasses_cache(monkeypatch):
    manager = SandboxManager()
    calls = {"n": 0}

    def fake_is_available():
        calls["n"] += 1
        return False

    monkeypatch.setattr(manager._docker, "is_available", fake_is_available)
    manager.docker_available()
    manager.docker_available(force_recheck=True)
    assert calls["n"] == 2


# -- workspace cleanup on failure (spec Part 35) -----------------------

def test_workspace_cleaned_up_even_on_command_failure(tmp_path, monkeypatch):
    manager = SandboxManager()
    monkeypatch.setattr(manager, "docker_available", lambda force_recheck=False: False)
    workspace_path_holder = {}

    from core.sandbox.workspace import SandboxWorkspace as RealWS

    class SpyWorkspace(RealWS):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            workspace_path_holder["path"] = self.path

    import core.sandbox.manager as manager_module
    original = manager_module.SandboxWorkspace
    manager_module.SandboxWorkspace = SpyWorkspace
    try:
        manager.execute_command(["python3", "-c", "import sys; sys.exit(1)"],
                                 risk_level=RiskLevel.MEDIUM, base_workspace_dir=tmp_path)
    finally:
        manager_module.SandboxWorkspace = original

    assert not workspace_path_holder["path"].exists()


# -- Docker integration (only when Docker is genuinely available) -------

@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker binary not found — NOT VERIFIED in this environment")
def test_docker_real_execution_smoke():
    sandbox = DockerSandbox()
    if not sandbox.is_available():
        pytest.skip("Docker binary present but daemon not reachable — NOT VERIFIED")
    with SandboxWorkspace() as ws:
        result = sandbox.execute_command(["echo", "hello from docker"], ws, ResourceLimits(timeout_seconds=30))
    assert result.success is True
    assert "hello from docker" in result.stdout
