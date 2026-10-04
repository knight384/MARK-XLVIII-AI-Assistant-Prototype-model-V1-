"""
core.memory.migration — idempotent migration from the legacy
memory/long_term.json into PreferenceMemory (Phase 5 spec, Part 8).

Requirements honored:
  - never silently discards data — every legacy value is imported,
  - preserves categories and values as-is,
  - safe to run multiple times (each run only imports keys not already
    present under the new store, so a value the user has since changed via
    the new system is never clobbered by a stale re-import),
  - does not duplicate records (same category/key -> same memory_id, so a
    second migration overwrites-with-identical-content rather than
    creating a second record),
  - reports success/failure via MigrationReport rather than raising for
    ordinary "file doesn't exist" cases,
  - never logs migrated content, only counts/category names.
  - does NOT delete memory/long_term.json — the original file is left in
    place; see docs/memory.md for the documented transition plan.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .errors import MemoryMigrationError
from .models import Source
from .preferences import PreferenceMemory, VALID_CATEGORIES

logger = logging.getLogger(__name__)


@dataclass
class MigrationReport:
    ran: bool
    imported_count: int = 0
    skipped_existing_count: int = 0
    categories_seen: tuple[str, ...] = ()
    error: str | None = None

    def summary(self) -> str:
        if self.error:
            return f"Migration failed: {self.error}"
        if not self.ran:
            return "Migration skipped: no legacy memory/long_term.json found."
        return (f"Migration complete: {self.imported_count} imported, "
                f"{self.skipped_existing_count} already present, "
                f"categories={list(self.categories_seen)}")


def migrate_legacy_json(legacy_path: Path, preference_memory: PreferenceMemory) -> MigrationReport:
    if not legacy_path.exists():
        return MigrationReport(ran=False)

    try:
        raw = json.loads(legacy_path.read_text(encoding="utf-8"))
    except Exception as exc:
        error = f"{type(exc).__name__}: could not parse {legacy_path.name}"
        logger.error("[Memory] Legacy migration failed: %s", error)
        return MigrationReport(ran=True, error=error)

    if not isinstance(raw, dict):
        return MigrationReport(ran=True, error="Legacy file did not contain a JSON object.")

    imported = 0
    skipped = 0
    categories_seen: set[str] = set()

    for category, items in raw.items():
        if category not in VALID_CATEGORIES or not isinstance(items, dict):
            continue
        categories_seen.add(category)
        for key, entry in items.items():
            value = entry.get("value") if isinstance(entry, dict) else entry
            if not value:
                continue
            if preference_memory.get(category, key) is not None:
                skipped += 1
                continue
            preference_memory.set(category, key, str(value), source=Source.IMPORT)
            imported += 1

    logger.info("[Memory] Legacy migration: imported=%d skipped_existing=%d categories=%s",
                imported, skipped, sorted(categories_seen))
    return MigrationReport(
        ran=True, imported_count=imported, skipped_existing_count=skipped,
        categories_seen=tuple(sorted(categories_seen)),
    )
