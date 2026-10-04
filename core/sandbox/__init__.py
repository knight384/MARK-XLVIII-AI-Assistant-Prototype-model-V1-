"""
core.sandbox — the execution isolation layer (Phase 6).

Typical usage:

    from core.sandbox import get_default_sandbox_manager, ResourceLimits
    from core.tools.metadata import RiskLevel

    manager = get_default_sandbox_manager()
    result = manager.execute_python("print('hi')", risk_level=RiskLevel.HIGH)
    print(result.stdout, result.exit_code)

See docs/sandbox.md for the Docker-vs-fallback decision and limitations.
"""
from .base import Sandbox
from .command import HostRestrictedSandbox
from .docker import DockerSandbox
from .errors import SandboxCancelledError, SandboxError, SandboxTimeoutError, SandboxUnavailableError
from .limits import ResourceLimits, SandboxResult
from .manager import SandboxManager, get_default_sandbox_manager
from .workspace import SandboxWorkspace

__all__ = [
    "Sandbox", "DockerSandbox", "HostRestrictedSandbox",
    "SandboxManager", "get_default_sandbox_manager",
    "ResourceLimits", "SandboxResult", "SandboxWorkspace",
    "SandboxError", "SandboxUnavailableError", "SandboxTimeoutError", "SandboxCancelledError",
]
