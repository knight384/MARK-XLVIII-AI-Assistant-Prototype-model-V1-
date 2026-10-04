"""
tests/memory/test_architecture.py — static checks (Phase 5 spec, Part 44).

Agents (core/agent/) must not directly import memory.memory_manager,
memory.config_manager, or open memory/long_term.json themselves — they use
MemoryService / AgentContext.memory.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_DIR = REPO_ROOT / "core" / "agent"
MEMORY_DIR = REPO_ROOT / "core" / "memory"


def _all_imports(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_agents_do_not_import_legacy_memory_manager():
    violations = []
    for py_file in AGENT_DIR.glob("*.py"):
        for imp in _all_imports(py_file):
            if imp == "memory.memory_manager" or imp == "memory" or imp.startswith("memory."):
                violations.append(f"{py_file.name}: imports '{imp}'")
    assert violations == [], f"Direct legacy memory imports found in core/agent/: {violations}"


def test_agents_do_not_construct_legacy_memory_path():
    """Real enforcement: no core/agent/ module constructs a path literal
    like 'long_term.json' as an actual Path/open() argument. Docstring
    mentions of the legacy file (e.g. explaining what Phase 5 replaced) are
    fine and intentionally not flagged here — the import-based tests above
    already cover functional coupling."""
    violations = []
    for py_file in AGENT_DIR.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for arg in node.args:
                    if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                            and "long_term.json" in arg.value):
                        violations.append(py_file.name)
    assert violations == [], f"core/agent/ constructs a legacy memory path: {violations}"


def test_agents_use_memory_service_not_raw_stores():
    """Confirms core/agent/ imports core.memory (the service), never
    core.memory.stores directly."""
    violations = []
    for py_file in AGENT_DIR.glob("*.py"):
        for imp in _all_imports(py_file):
            if imp.startswith("core.memory.stores"):
                violations.append(f"{py_file.name}: imports '{imp}'")
    assert violations == [], f"core/agent/ imports a MemoryStore directly: {violations}"


def test_actions_computer_control_no_longer_reads_legacy_file_directly():
    """Phase 5 explicitly fixed this call site (see core/agent audit) —
    confirm no Path/open() call constructs the legacy file path (a
    docstring mentioning the fix, as this file itself now has, is fine)."""
    path = REPO_ROOT / "actions" / "computer_control.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "long_term.json" in arg.value:
                    assert False, "computer_control.py still constructs the legacy memory path"
    assert "get_default_memory_service" in path.read_text(encoding="utf-8")


def test_save_memory_tool_uses_new_memory_service():
    src = (REPO_ROOT / "core" / "tools" / "definitions.py").read_text(encoding="utf-8")
    assert "from core.memory import get_default_memory_service" in src
    assert "from memory.memory_manager import update_memory" not in src


def test_memory_stores_are_only_constructed_within_core_memory():
    """Nothing outside core/memory/ should construct a MemoryStore
    directly (spec Part 1: 'Memory is a service, not a file')."""
    violations = []
    for py_file in REPO_ROOT.rglob("*.py"):
        if MEMORY_DIR in py_file.parents or "tests" in py_file.parts or ".git" in py_file.parts:
            continue
        for imp in _all_imports(py_file):
            if imp.startswith("core.memory.stores"):
                violations.append(f"{py_file.relative_to(REPO_ROOT)}: imports '{imp}'")
    assert violations == [], f"MemoryStore constructed outside core/memory/: {violations}"
