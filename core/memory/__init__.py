"""
core.memory — the layered memory subsystem (Phase 5).

Typical usage:

    from core.memory import get_default_memory_service, MemoryType, RetrievalQuery

    memory = get_default_memory_service()
    memory.remember("User prefers dark mode.", MemoryType.PREFERENCE, source=Source.USER)
    results = memory.retrieve(RetrievalQuery(query="dark mode", memory_types=(MemoryType.PREFERENCE,)))

Agents access it via `AgentContext.memory` (see core/agent/context.py) rather
than constructing their own MemoryService or touching a MemoryStore/JSON
file directly.
"""
from .errors import (
    MemoryError, MemoryMigrationError, MemoryNotFoundError, MemoryRetrievalError,
    MemoryStorageError, MemoryValidationError,
)
from .models import MemoryRecord, MemoryType, RetrievalQuery, RetrievalResult, Source
from .policies import MemoryConfig, load_memory_config, should_record_episodic
from .service import MemoryService, get_default_memory_service

__all__ = [
    "MemoryService", "get_default_memory_service",
    "MemoryRecord", "MemoryType", "Source", "RetrievalQuery", "RetrievalResult",
    "MemoryConfig", "load_memory_config", "should_record_episodic",
    "MemoryError", "MemoryNotFoundError", "MemoryValidationError",
    "MemoryStorageError", "MemoryRetrievalError", "MemoryMigrationError",
]
