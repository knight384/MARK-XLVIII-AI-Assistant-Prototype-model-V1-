"""core.sandbox.limits — resource limits and structured sandbox result (Phase 6 spec, Parts 31, 34)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceLimits:
    timeout_seconds: float = 30.0
    cpu_limit: float = 1.0             # CPU cores (Docker: --cpus)
    memory_limit_mb: int = 512
    process_limit: int = 64
    output_limit_bytes: int = 1_000_000  # stdout+stderr combined cap
    network_enabled: bool = False       # spec Part 30: default DENY


@dataclass
class SandboxResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: float = 0.0
    timed_out: bool = False
    cancelled: bool = False
    backend: str = ""                   # "docker" | "host_restricted"
    error: str = ""

    def truncated(self, limit: int) -> "SandboxResult":
        self.stdout = self.stdout[:limit]
        self.stderr = self.stderr[:limit]
        return self
