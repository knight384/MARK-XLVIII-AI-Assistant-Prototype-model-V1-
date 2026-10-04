"""
tests/agent/test_architecture.py — static checks (Phase 4 spec, Part 42).

Agents must go through the Model Gateway and Tool Registry/Executor —
never a provider SDK or `actions.*` module directly.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_DIR = REPO_ROOT / "core" / "agent"

_FORBIDDEN_PROVIDER_IMPORTS = {"google", "google.genai", "openai", "anthropic", "ollama"}


def _all_imports(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_no_direct_provider_sdk_imports_in_agent_layer():
    violations = []
    for py_file in AGENT_DIR.glob("*.py"):
        for imp in _all_imports(py_file):
            top_level = imp.split(".")[0]
            if top_level in _FORBIDDEN_PROVIDER_IMPORTS or imp in _FORBIDDEN_PROVIDER_IMPORTS:
                violations.append(f"{py_file.name}: imports '{imp}'")
    assert violations == [], f"Direct provider SDK imports found: {violations}"


def test_no_direct_actions_imports_in_agent_layer():
    """Agents must use the Tool Registry/Executor, never `actions.*` directly
    (spec Part 3, 34). The tool wrappers themselves (core/tools/definitions.py)
    are exempt — that's Phase 3's designated integration point."""
    violations = []
    for py_file in AGENT_DIR.glob("*.py"):
        for imp in _all_imports(py_file):
            if imp == "actions" or imp.startswith("actions."):
                violations.append(f"{py_file.name}: imports '{imp}'")
    assert violations == [], f"Direct actions.* imports found in core/agent/: {violations}"


def test_agents_use_model_gateway_module_for_generation():
    """Every agent-layer module that calls a model does so via
    core.llm.gateway/core.llm.types — confirms the integration point exists
    (a purely structural smoke check, not a behavior test)."""
    gateway_file = REPO_ROOT / "core" / "llm" / "gateway.py"
    assert gateway_file.exists()

    base_py = (AGENT_DIR / "base.py").read_text(encoding="utf-8")
    assert "core.llm.types" in base_py  # ToolUsingAgent._decide_tool_call uses ModelRequest/Message
    assert "context.model_gateway.generate(" in base_py

    planner_py = (AGENT_DIR / "planner.py").read_text(encoding="utf-8")
    assert "core.llm.gateway" in planner_py
    assert "self._gateway.generate(" in planner_py


def test_agents_use_tool_executor_not_a_duplicate():
    """Confirms no AgentToolExecutor/DeveloperToolExecutor-style duplicate
    exists anywhere in core/agent/ (spec Part 34)."""
    for py_file in AGENT_DIR.glob("*.py"):
        src = py_file.read_text(encoding="utf-8")
        assert "class ToolExecutor" not in src, f"{py_file.name} defines a duplicate ToolExecutor"
    base_py = (AGENT_DIR / "base.py").read_text(encoding="utf-8")
    assert "context.tool_executor.execute(" in base_py
