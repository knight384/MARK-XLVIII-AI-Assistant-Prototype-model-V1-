"""core.memory.errors — memory-specific error taxonomy (Phase 5 spec, Part 40)."""
from __future__ import annotations


class MemoryError(Exception):
    def __init__(self, message: str, *, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


class MemoryNotFoundError(MemoryError):
    pass


class MemoryValidationError(MemoryError):
    pass


class MemoryStorageError(MemoryError):
    pass


class MemoryRetrievalError(MemoryError):
    pass


class MemoryMigrationError(MemoryError):
    pass
