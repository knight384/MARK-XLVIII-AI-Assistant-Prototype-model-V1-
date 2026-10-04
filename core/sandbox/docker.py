"""
core.sandbox.docker — Docker-backed sandbox (Phase 6 spec, Part 24).

**Decision: Docker CLI (subprocess) over the `docker` Python SDK** (spec
Part 65). Rationale, documented here and in docs/sandbox.md:
  - Zero new pip dependency — `docker` isn't already in requirements.txt,
    and the CLI (`docker run ...`) gives us everything this needs
    (resource limits, network mode, volume mounts, timeouts via process
    control) without adding a client library + its own version-compat
    surface with the Docker Engine API.
  - Simpler error handling: a non-zero exit code / stderr from `docker run`
    is easier to reason about than an SDK exception hierarchy for a
    single-purpose "run this, capture output" use case.
  - Easier to test/reason about on Windows (this is a Windows-first app,
    spec Part 66) — CLI behavior is identical whether Docker Desktop
    exposes a named pipe or a TCP socket; the SDK's transport auto-
    detection is one more thing that can silently misconfigure.
  - Portability: the same `docker` binary invocation works via WSL2 /
    Docker Desktop / native Linux Docker without SDK-specific setup.

This is real isolation (`is_real_isolation = True`): default `--network
none`, memory/CPU/pids limits, no host filesystem mounts beyond the single
workspace directory, no added capabilities.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time

from core.tools.base import CancellationToken

from .base import Sandbox
from .limits import ResourceLimits, SandboxResult
from .workspace import SandboxWorkspace

logger = logging.getLogger(__name__)

_DEFAULT_IMAGE = "python:3.12-slim"


class DockerSandbox(Sandbox):
    backend_name = "docker"
    is_real_isolation = True

    def __init__(self, image: str = _DEFAULT_IMAGE):
        self._image = image
        self._docker_path = shutil.which("docker")

    def is_available(self) -> bool:
        if not self._docker_path:
            return False
        try:
            result = subprocess.run([self._docker_path, "info"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def execute_command(
        self,
        command: list[str],
        workspace: SandboxWorkspace,
        limits: ResourceLimits,
        cancellation_token: CancellationToken | None = None,
    ) -> SandboxResult:
        if not self.is_available():
            return SandboxResult(success=False, backend=self.backend_name,
                                  error="Docker is not available on this system.")

        container_name = f"jarvis-sandbox-{workspace.workspace_id}"
        docker_cmd = [
            self._docker_path, "run", "--rm",
            "--name", container_name,
            "-v", f"{workspace.path}:/workspace",
            "-w", "/workspace",
            "--memory", f"{limits.memory_limit_mb}m",
            "--cpus", str(limits.cpu_limit),
            "--pids-limit", str(limits.process_limit),
            "--network", "bridge" if limits.network_enabled else "none",
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
        ]
        docker_cmd += [self._image] + command

        t0 = time.perf_counter()
        proc = None
        try:
            proc = subprocess.Popen(docker_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                stdout, stderr = proc.communicate(timeout=limits.timeout_seconds)
                timed_out = False
            except subprocess.TimeoutExpired:
                timed_out = True
                stdout, stderr = self._kill_and_drain(proc, container_name)

            if cancellation_token is not None and cancellation_token.is_cancelled and not timed_out:
                self._force_kill(container_name)

            duration_ms = (time.perf_counter() - t0) * 1000
            exit_code = proc.returncode

            return SandboxResult(
                success=(not timed_out and exit_code == 0),
                stdout=(stdout or "")[:limits.output_limit_bytes],
                stderr=(stderr or "")[:limits.output_limit_bytes],
                exit_code=exit_code, duration_ms=duration_ms, timed_out=timed_out,
                backend=self.backend_name,
            )
        except Exception as exc:
            self._force_kill(container_name)
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.error("[DockerSandbox] execution failed: %s", exc)
            return SandboxResult(success=False, backend=self.backend_name,
                                  duration_ms=duration_ms, error=str(exc))
        finally:
            # Belt-and-suspenders: --rm handles normal exit, but guarantee
            # cleanup even on an abnormal path (spec Part 35).
            self._force_kill(container_name)

    def _kill_and_drain(self, proc: subprocess.Popen, container_name: str) -> tuple[str, str]:
        self._force_kill(container_name)
        try:
            return proc.communicate(timeout=5)
        except Exception:
            return "", ""

    def _force_kill(self, container_name: str) -> None:
        if not self._docker_path:
            return
        try:
            subprocess.run([self._docker_path, "kill", container_name],
                            capture_output=True, timeout=5)
        except Exception:
            pass  # container may already be gone — that's fine
