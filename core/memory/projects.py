"""
core.memory.projects — project-scoped memory (Phase 5 spec, Parts 16-17).

Project identity (Part 17): rather than rely on folder names, a project_id
is derived, in priority order, from: (1) an explicit project_id the caller
supplies, (2) the repository's Git remote URL if available, (3) the
repository root's absolute path. This is the simplest stable approach that
doesn't require a new manifest format — a Git remote is stable across
clones/machines when available; the absolute path is a reasonable fallback
for non-Git or not-yet-pushed projects.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .models import MemoryRecord, MemoryType, Source
from .stores.base import MemoryStore


def derive_project_id(repo_path: str | Path, explicit_id: str | None = None) -> str:
    if explicit_id:
        return explicit_id

    repo_path = Path(repo_path).resolve()
    try:
        remote = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=3,
        )
        if remote.returncode == 0 and remote.stdout.strip():
            return "git:" + hashlib.sha1(remote.stdout.strip().encode()).hexdigest()[:16]
    except Exception:
        pass  # git not available / not a repo / timed out — fall through to path-based id

    return "path:" + hashlib.sha1(str(repo_path).encode()).hexdigest()[:16]


class ProjectMemory:
    def __init__(self, store: MemoryStore):
        self._store = store

    def set_fact(self, project_id: str, field: str, value: str, source: Source = Source.AGENT,
                 importance: float = 0.6) -> MemoryRecord:
        """`field` is a free-form key such as 'architecture', 'tech_stack',
        'known_issue', 'testing_state', 'deployment_info', etc. — spec Part
        16 lists example fields but doesn't mandate a fixed schema."""
        record = MemoryRecord(
            content=value, memory_type=MemoryType.PROJECT, summary=field,
            source=source, importance=importance, namespace=f"project:{project_id}",
            project_id=project_id, metadata={"field": field},
        )
        self._store.save(record)
        return record

    def get_facts(self, project_id: str, field: str | None = None) -> list[MemoryRecord]:
        records = self._store.search(memory_types=(MemoryType.PROJECT,), project_id=project_id)
        if field is not None:
            records = [r for r in records if r.metadata.get("field") == field]
        return records

    def forget_project(self, project_id: str) -> int:
        return self._store.delete_by_project(project_id)
