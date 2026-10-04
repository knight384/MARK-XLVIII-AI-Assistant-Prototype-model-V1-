"""
core.sandbox.workspace — isolated per-execution workspace (Phase 6 spec,
Part 28-29). No unrelated user directories, no credential stores, no
browser profiles — only this workspace directory by default.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class SandboxWorkspace:
    def __init__(self, base_dir: Path | None = None):
        base_dir = base_dir or Path(tempfile.gettempdir()) / "jarvis_sandbox"
        base_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_id = uuid.uuid4().hex[:12]
        self.path = base_dir / self.workspace_id
        self.path.mkdir(parents=True, exist_ok=False)

    def resolve(self, relative_path: str) -> Path:
        """Resolves a path *inside* the workspace only — refuses anything
        that would escape it (spec Part 28: 'path traversal protection')."""
        candidate = (self.path / relative_path).resolve()
        if self.path.resolve() not in candidate.parents and candidate != self.path.resolve():
            raise ValueError(f"Path '{relative_path}' escapes the sandbox workspace.")
        return candidate

    def write_file(self, relative_path: str, content: str) -> Path:
        target = self.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def read_file(self, relative_path: str) -> str:
        return self.resolve(relative_path).read_text(encoding="utf-8")

    def cleanup(self) -> None:
        try:
            if self.path.exists():
                shutil.rmtree(self.path, ignore_errors=True)
        except Exception as exc:
            logger.warning("[Sandbox] Failed to clean up workspace %s: %s", self.path, exc)

    def __enter__(self) -> "SandboxWorkspace":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()
