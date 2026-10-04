"""
memory.memory_manager — DEPRECATED compatibility shim (Phase 5).

This module used to be the sole implementation of user-fact memory,
reading/writing memory/long_term.json directly. As of Phase 5, the real
implementation lives in core/memory/ (see core/memory/preferences.py and
core/memory/service.py) — this module now only re-exports the same public
function names/signatures, delegating to the new MemoryService, so any
code that still imports from here (main.py, actions/proactive.py) keeps
working unchanged (Phase 5 spec, Part 7: "Provide backward-compatible APIs
temporarily if the old code still expects them").

New code should use `core.memory.get_default_memory_service()` directly
instead of importing from this module. Do not add new functionality here —
add it to core/memory/ and, if truly needed for compatibility, expose a
thin wrapper here.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

VALID_CATEGORIES = ("identity", "preferences", "projects", "relationships", "wishes", "notes")
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200


def _service():
    from core.memory import get_default_memory_service
    return get_default_memory_service()


def load_memory() -> dict:
    """Returns the legacy categorized-dict shape, sourced from the new
    PreferenceMemory layer instead of a direct file read."""
    return _service().preferences.as_categorized_dict()


def save_memory(memory: dict) -> None:
    """Legacy bulk-save signature. Writes every (category, key) pair found
    in `memory` through the new PreferenceMemory layer. Prefer
    `update_memory()` or `core.memory`'s MemoryService directly in new code."""
    from core.memory.models import Source
    service = _service()
    for category, items in (memory or {}).items():
        if category not in VALID_CATEGORIES or not isinstance(items, dict):
            continue
        for key, entry in items.items():
            value = entry.get("value") if isinstance(entry, dict) else entry
            if value:
                service.preferences.set(category, key, str(value), source=Source.SYSTEM)


def update_memory(memory_update: dict) -> dict:
    """Legacy recursive-update signature (category -> key -> {"value": ...}
    or category -> key -> value). Returns the resulting categorized dict,
    matching the prior return contract."""
    from core.memory.models import Source
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()

    service = _service()
    changed_categories = []
    for category, items in memory_update.items():
        if category not in VALID_CATEGORIES or not isinstance(items, dict):
            continue
        for key, entry in items.items():
            value = entry.get("value") if isinstance(entry, dict) else entry
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            service.preferences.set(category, key, str(value), source=Source.USER)
            changed_categories.append(category)

    if changed_categories:
        logger.info("[Memory] Saved: %s", sorted(set(changed_categories)))
    return load_memory()


def format_memory_for_prompt(memory: dict | None = None) -> str:
    """`memory` argument is accepted for signature compatibility but
    ignored — the new PreferenceMemory layer is always the live source of
    truth, so a stale dict passed in by an old caller can't drift from it."""
    return _service().preferences.format_for_prompt()


def remember(key: str, value: str, category: str = "notes") -> str:
    if category not in VALID_CATEGORIES:
        category = "notes"
    from core.memory.models import Source
    _service().preferences.set(category, key, value, source=Source.USER)
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    existed = _service().preferences.forget(category, key)
    return f"Forgotten: {category}/{key}" if existed else f"Not found: {category}/{key}"


forget_memory = forget
