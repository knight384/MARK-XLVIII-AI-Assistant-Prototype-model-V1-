"""tests/memory/conftest.py — isolated, temp-dir-backed memory fixtures."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.memory.policies import MemoryConfig
from core.memory.service import MemoryService
from core.memory.stores.json_store import JsonMemoryStore
from core.memory.stores.sqlite_store import SqliteMemoryStore


@pytest.fixture
def tmp_memory_dir(tmp_path) -> Path:
    return tmp_path


@pytest.fixture
def preference_store(tmp_memory_dir) -> JsonMemoryStore:
    return JsonMemoryStore(tmp_memory_dir / "preferences.json")


@pytest.fixture
def durable_store(tmp_memory_dir) -> SqliteMemoryStore:
    return SqliteMemoryStore(tmp_memory_dir / "memory.db")


@pytest.fixture
def memory_service(preference_store, durable_store) -> MemoryService:
    return MemoryService(preference_store, durable_store, config=MemoryConfig())


@pytest.fixture
def memory_service_disabled(preference_store, durable_store) -> MemoryService:
    return MemoryService(preference_store, durable_store, config=MemoryConfig(memory_enabled=False))
