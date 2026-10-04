"""
core.tools.metadata — formal tool metadata (Phase 3 spec, Part 8).

Risk classification is seeded directly from the Phase 0 security audit's
KEEP/REFACTOR/REBUILD matrix and security assessment. This is METADATA ONLY
— no approval workflow, policy engine, or enforcement exists yet (that's
Phase 6). A tool declaring risk_level=CRITICAL still executes exactly as it
did before Phase 3; the metadata just makes that classification visible and
queryable for future phases to act on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ToolCategory(str, Enum):
    COMPUTER = "computer"
    BROWSER = "browser"
    FILESYSTEM = "filesystem"
    COMMUNICATION = "communication"
    WEB = "web"
    MEDIA = "media"
    SYSTEM = "system"
    DEVELOPER = "developer"
    VISION = "vision"
    PRODUCTIVITY = "productivity"
    MEMORY = "memory"


class Capability(str, Enum):
    READ = "read"
    WRITE = "write"
    NETWORK = "network"
    COMPUTER_CONTROL = "computer_control"
    BROWSER_CONTROL = "browser_control"
    PROCESS_EXECUTION = "process_execution"
    CAMERA = "camera"
    MICROPHONE = "microphone"
    FILESYSTEM = "filesystem"
    CODE_EXECUTION = "code_execution"


@dataclass(frozen=True)
class ToolMetadata:
    category: ToolCategory
    risk_level: RiskLevel
    capabilities: tuple[Capability, ...] = ()
    timeout_seconds: float | None = 60.0
    supports_cancellation: bool = False
    requires_confirmation: bool = False   # not enforced yet — Phase 6 will read this
    supports_verification: bool = False
    supports_dry_run: bool = False
    permissions: tuple[str, ...] = ()      # free-form permission tags, for future policy engine
    notes: str = ""                        # e.g. "timeout NOT SAFE — leaves partial OS state if cancelled"
    requires_sandbox: bool = False         # Phase 6: this tool's dangerous path must run through SandboxManager
