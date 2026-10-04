"""
core.memory.preferences — user preference/fact memory (Phase 5 spec, Part
7). Preserves the exact category semantics of the pre-Phase-5
memory/memory_manager.py: identity, preferences, projects, relationships,
wishes, notes — plus its size-control intent (a per-value length cap and a
total-size cap that trims oldest entries first) and its
`format_memory_for_prompt()` output shape, since that text is injected
directly into the Gemini Live system prompt and changing its format would
be an unnecessary behavioral change.

Backed by JsonMemoryStore (see core/memory/stores/json_store.py) — one
MemoryRecord per (category, key) pair, namespace="user".
"""
from __future__ import annotations

import logging
import time

from .models import MemoryRecord, MemoryType, Source
from .stores.base import MemoryStore

logger = logging.getLogger(__name__)

VALID_CATEGORIES = ("identity", "preferences", "projects", "relationships", "wishes", "notes")
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200      # total character budget across all preference records, matching the legacy limit

_ID_FIELD_ORDER = ("name", "age", "birthday", "city", "job", "language", "school", "nationality")


def _record_id(category: str, key: str) -> str:
    return f"pref:{category}:{key}"


class PreferenceMemory:
    def __init__(self, store: MemoryStore):
        self._store = store

    def set(self, category: str, key: str, value: str, source: Source = Source.USER) -> MemoryRecord:
        if category not in VALID_CATEGORIES:
            category = "notes"
        value = _truncate_value(value)
        record = MemoryRecord(
            content=value, memory_type=MemoryType.PREFERENCE, memory_id=_record_id(category, key),
            namespace="user", source=source, importance=0.7,
            metadata={"category": category, "key": key},
        )
        self._store.save(record)
        self._enforce_total_limit()
        return record

    def get(self, category: str, key: str) -> str | None:
        record = self._store.get(_record_id(category, key))
        return record.content if record else None

    def forget(self, category: str, key: str) -> bool:
        return self._store.delete(_record_id(category, key))

    def as_categorized_dict(self) -> dict[str, dict[str, dict]]:
        """Shape-compatible with the legacy memory_manager.py structure:
        {category: {key: {"value": ..., "updated": "YYYY-MM-DD"}}}."""
        out: dict[str, dict[str, dict]] = {c: {} for c in VALID_CATEGORIES}
        for record in self._store.search(memory_types=(MemoryType.PREFERENCE,), namespace="user"):
            category = record.metadata.get("category", "notes")
            key = record.metadata.get("key", record.memory_id)
            if category not in out:
                out[category] = {}
            out[category][key] = {
                "value": record.content,
                "updated": time.strftime("%Y-%m-%d", time.localtime(record.updated_at)),
            }
        return out

    def format_for_prompt(self) -> str:
        """Reproduces memory_manager.py's format_memory_for_prompt() output
        exactly — this text is injected into the Gemini Live system prompt,
        so its shape is a deliberate compatibility contract, not just an
        implementation detail."""
        memory = self.as_categorized_dict()
        lines: list[str] = []

        identity = memory.get("identity", {})
        for field in _ID_FIELD_ORDER:
            entry = identity.get(field)
            if entry:
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    lines.append(f"{field.title()}: {val}")
        for key, entry in identity.items():
            if key in _ID_FIELD_ORDER:
                continue
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{key.replace('_', ' ').title()}: {val}")

        prefs = memory.get("preferences", {})
        if prefs:
            lines.append("")
            lines.append("Preferences:")
            for key, entry in list(prefs.items())[:15]:
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

        projects = memory.get("projects", {})
        if projects:
            lines.append("")
            lines.append("Active Projects / Goals:")
            for key, entry in list(projects.items())[:8]:
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

        rels = memory.get("relationships", {})
        if rels:
            lines.append("")
            lines.append("People in their life:")
            for key, entry in list(rels.items())[:10]:
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

        wishes = memory.get("wishes", {})
        if wishes:
            lines.append("")
            lines.append("Wishes / Plans / Wants:")
            for key, entry in list(wishes.items())[:8]:
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

        notes = memory.get("notes", {})
        if notes:
            lines.append("")
            lines.append("Other notes:")
            for key, entry in list(notes.items())[:8]:
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    lines.append(f"  - {key}: {val}")

        if not lines:
            return ""

        header = "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]\n"
        result = header + "\n".join(lines)
        if len(result) > 2000:
            result = result[:1997] + "…"
        return result + "\n"

    def identity_fields(self) -> dict[str, str]:
        """Used by computer_control.py's user_data action — replaces its
        prior direct read of memory/long_term.json."""
        identity = self.as_categorized_dict().get("identity", {})
        return {k: v.get("value", "") for k, v in identity.items()}

    def _enforce_total_limit(self) -> None:
        records = self._store.search(memory_types=(MemoryType.PREFERENCE,), namespace="user")
        total_chars = sum(len(r.content) for r in records)
        if total_chars <= MEMORY_MAX_CHARS:
            return
        records.sort(key=lambda r: r.updated_at)  # oldest first, matches legacy _trim_to_limit behavior
        for record in records:
            if total_chars <= MEMORY_MAX_CHARS:
                break
            self._store.delete(record.memory_id)
            total_chars -= len(record.content)
            logger.info("[Memory] Trimmed preference %s/%s (total size limit)",
                        record.metadata.get("category"), record.metadata.get("key"))


def _truncate_value(value: str) -> str:
    if isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
        return value[:MAX_VALUE_LENGTH].rstrip() + "…"
    return value
