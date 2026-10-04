"""
core.sandbox.manager — SandboxManager (Phase 6 spec, Part 24). Picks
Docker when available; falls back to the host-restricted backend only when
policy permits it for the given risk level. Lazily probes Docker
availability (spec Part 68 — don't add startup latency) and caches the
result briefly.
"""
from __future__ import annotations

import logging
import threading
import time

from core.tools.base import CancellationToken
from core.tools.metadata import RiskLevel

from .base import Sandbox
from .docker import DockerSandbox
from .errors import SandboxUnavailableError
from .limits import ResourceLimits, SandboxResult
from .workspace import SandboxWorkspace

logger = logging.getLogger(__name__)

_PROBE_CACHE_SECONDS = 30.0

# Risk levels for which the weak host-process fallback is acceptable when
# Docker is unavailable — CRITICAL always requires real isolation (spec
# Part 25: "The system should be able to refuse dangerous execution if no
# safe sandbox is available.").
_FALLBACK_ACCEPTABLE_FOR = (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH)


class SandboxManager:
    def __init__(self, docker_sandbox: Sandbox | None = None, fallback_sandbox: Sandbox | None = None):
        from .command import HostRestrictedSandbox
        self._docker = docker_sandbox or DockerSandbox()
        self._fallback = fallback_sandbox or HostRestrictedSandbox()
        self._probe_lock = threading.Lock()
        self._docker_available: bool | None = None
        self._probed_at: float = 0.0

    def docker_available(self, force_recheck: bool = False) -> bool:
        with self._probe_lock:
            now = time.monotonic()
            if not force_recheck and self._docker_available is not None and (now - self._probed_at) < _PROBE_CACHE_SECONDS:
                return self._docker_available
            self._docker_available = self._docker.is_available()
            self._probed_at = now
            return self._docker_available

    def select_backend(self, risk_level: RiskLevel) -> Sandbox | None:
        """Returns the backend to use, or None if nothing acceptable is
        available for this risk level (caller should treat that as
        'refuse to execute', matching PolicyEngine's
        rule_sandbox_required_unavailable)."""
        if self.docker_available():
            return self._docker
        if risk_level in _FALLBACK_ACCEPTABLE_FOR:
            logger.warning(
                "[SandboxManager] Docker unavailable — using host_restricted fallback for "
                "%s-risk execution. This is NOT a real security boundary.", risk_level.value,
            )
            return self._fallback
        return None

    def execute_command(
        self,
        command: list[str],
        risk_level: RiskLevel,
        limits: ResourceLimits | None = None,
        cancellation_token: CancellationToken | None = None,
        base_workspace_dir=None,
    ) -> SandboxResult:
        limits = limits or ResourceLimits()
        backend = self.select_backend(risk_level)
        if backend is None:
            raise SandboxUnavailableError(
                f"No sandbox backend is available/acceptable for {risk_level.value}-risk execution "
                f"(Docker unavailable, and the host-restricted fallback is not permitted at this risk level)."
            )
        with SandboxWorkspace(base_dir=base_workspace_dir) as workspace:
            return backend.execute_command(command, workspace, limits, cancellation_token)

    def execute_command_in_dir(
        self,
        command: list[str],
        risk_level: RiskLevel,
        working_dir,
        limits: ResourceLimits | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> SandboxResult:
        """Like execute_command(), but runs against an EXISTING directory
        (e.g. a DeveloperAgent-built project) instead of a throwaway
        temp workspace — the directory is never created or deleted by this
        call. Used for dev_agent.py's model-planned run commands, where the
        code being run needs to be the actual project directory, not a
        fresh sandbox copy (spec Part 27/58)."""
        from pathlib import Path
        limits = limits or ResourceLimits()
        backend = self.select_backend(risk_level)
        if backend is None:
            raise SandboxUnavailableError(
                f"No sandbox backend is available/acceptable for {risk_level.value}-risk execution."
            )

        class _ExistingDirWorkspace:
            """A minimal stand-in for SandboxWorkspace that points at an
            existing directory rather than owning/creating/deleting one."""
            def __init__(self, path):
                self.path = Path(path)
                self.workspace_id = self.path.name

            def resolve(self, relative_path: str):
                candidate = (self.path / relative_path).resolve()
                if self.path.resolve() not in candidate.parents and candidate != self.path.resolve():
                    raise ValueError(f"Path '{relative_path}' escapes the working directory.")
                return candidate

        return backend.execute_command(command, _ExistingDirWorkspace(working_dir), limits, cancellation_token)

    def execute_python(
        self,
        code: str,
        risk_level: RiskLevel,
        limits: ResourceLimits | None = None,
        cancellation_token: CancellationToken | None = None,
        base_workspace_dir=None,
    ) -> SandboxResult:
        limits = limits or ResourceLimits()
        backend = self.select_backend(risk_level)
        if backend is None:
            raise SandboxUnavailableError(
                f"No sandbox backend is available/acceptable for {risk_level.value}-risk execution."
            )
        with SandboxWorkspace(base_dir=base_workspace_dir) as workspace:
            return backend.execute_python(code, workspace, limits, cancellation_token)


_default_manager: SandboxManager | None = None
_default_lock = threading.Lock()


def get_default_sandbox_manager() -> SandboxManager:
    global _default_manager
    with _default_lock:
        if _default_manager is None:
            _default_manager = SandboxManager()
        return _default_manager
