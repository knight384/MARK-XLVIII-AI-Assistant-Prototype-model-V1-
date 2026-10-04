"""core.sandbox.base — the Sandbox interface (Phase 6 spec, Part 24)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.tools.base import CancellationToken

from .limits import ResourceLimits, SandboxResult
from .workspace import SandboxWorkspace


class Sandbox(ABC):
    backend_name: str = "base"

    #: Whether this backend provides REAL isolation (spec Part 25/67 — a
    #: host-process fallback must never claim to be equivalent to Docker).
    is_real_isolation: bool = False

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def execute_command(
        self,
        command: list[str],
        workspace: SandboxWorkspace,
        limits: ResourceLimits,
        cancellation_token: CancellationToken | None = None,
    ) -> SandboxResult:
        """Runs `command` (an argv list — never a shell string, spec Part
        33) with `workspace.path` as the working directory, under `limits`.
        Must always clean up (spec Part 35) and must terminate on timeout
        (Part 37) and cancellation (Part 36) — never leave an orphaned
        process/container."""
        raise NotImplementedError

    def execute_python(
        self,
        code: str,
        workspace: SandboxWorkspace,
        limits: ResourceLimits,
        cancellation_token: CancellationToken | None = None,
    ) -> SandboxResult:
        """Convenience: writes `code` into the workspace and runs it with
        the sandboxed Python interpreter. Default implementation in terms
        of execute_command(); backends may override for efficiency."""
        workspace.write_file("_generated.py", code)
        return self.execute_command(["python3", "_generated.py"], workspace, limits, cancellation_token)
