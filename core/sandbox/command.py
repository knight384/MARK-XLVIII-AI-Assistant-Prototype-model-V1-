"""
core.sandbox.command — the host-restricted fallback sandbox (Phase 6 spec,
Part 25).

**A host-process fallback is NOT equivalent to a real security sandbox.**
This class exists only so JARVIS can still run *trusted-ish, low-risk*
generated code when Docker is unavailable, with the best restriction a
plain OS subprocess can offer: no shell interpretation, a scoped working
directory, environment variable stripping, and a hard timeout. It provides
NO filesystem isolation (the process can still read/write anywhere the
OS user account can), NO network isolation, and NO memory/CPU containment
on Windows (the `resource` module used for rlimits on POSIX doesn't exist
there). `is_real_isolation = False` is load-bearing: the PolicyEngine and
callers use this flag to decide whether this backend is acceptable for a
given risk level — see core/sandbox/manager.py's policy, which refuses to
use this fallback for CRITICAL-risk requests by default.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import time

from core.tools.base import CancellationToken

from .base import Sandbox
from .limits import ResourceLimits, SandboxResult

logger = logging.getLogger(__name__)


class HostRestrictedSandbox(Sandbox):
    backend_name = "host_restricted"
    is_real_isolation = False

    def is_available(self) -> bool:
        return True  # always "available" in the sense that subprocess exists — NOT that it's safe

    def execute_command(
        self,
        command: list[str],
        workspace,
        limits: ResourceLimits,
        cancellation_token: CancellationToken | None = None,
    ) -> SandboxResult:
        t0 = time.perf_counter()

        # Strip environment down to the minimum needed to run an
        # interpreter — no inherited API keys/tokens from the parent
        # process's environment (defense in depth; not a real boundary).
        restricted_env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),  # required for Python to start on Windows
        }

        preexec_fn = None
        if platform.system() != "Windows":
            preexec_fn = _apply_posix_limits(limits)

        proc = None
        try:
            proc = subprocess.Popen(
                command, cwd=str(workspace.path), env=restricted_env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                shell=False,  # never shell=True for generated commands (spec Part 33)
                preexec_fn=preexec_fn,
            )
            try:
                stdout, stderr = proc.communicate(timeout=limits.timeout_seconds)
                timed_out = False
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=5)
                timed_out = True

            cancelled = bool(cancellation_token and cancellation_token.is_cancelled)
            if cancelled and proc.poll() is None:
                proc.kill()

            duration_ms = (time.perf_counter() - t0) * 1000
            return SandboxResult(
                success=(not timed_out and not cancelled and proc.returncode == 0),
                stdout=(stdout or "")[:limits.output_limit_bytes],
                stderr=(stderr or "")[:limits.output_limit_bytes],
                exit_code=proc.returncode, duration_ms=duration_ms,
                timed_out=timed_out, cancelled=cancelled, backend=self.backend_name,
            )
        except Exception as exc:
            if proc is not None and proc.poll() is None:
                proc.kill()
            logger.error("[HostRestrictedSandbox] execution failed: %s", exc)
            return SandboxResult(success=False, backend=self.backend_name, error=str(exc))


def _apply_posix_limits(limits: ResourceLimits):
    """Returns a preexec_fn applying best-effort POSIX rlimits. Not
    available on Windows — see module docstring."""
    def _limit():
        try:
            import resource
            mem_bytes = limits.memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_NPROC, (limits.process_limit, limits.process_limit))
        except Exception:
            pass  # best-effort only — never block execution over a missing rlimit
    return _limit
