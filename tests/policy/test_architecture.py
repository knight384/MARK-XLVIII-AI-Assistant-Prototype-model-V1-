"""
tests/policy/test_architecture.py — Phase 6 spec Parts 18, 42, 56-57 static
checks: no dangerous execution path bypasses ToolRegistry -> ToolExecutor
-> PolicyEngine, and no direct provider SDK/actions.* imports in the agent
layer (re-confirmed post-Phase-6).
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_DIR = REPO_ROOT / "core" / "agent"
TOOLS_DIR = REPO_ROOT / "core" / "tools"


def _all_imports(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_agents_still_have_no_direct_actions_imports():
    violations = []
    for py_file in AGENT_DIR.glob("*.py"):
        for imp in _all_imports(py_file):
            if imp == "actions" or imp.startswith("actions."):
                violations.append(f"{py_file.name}: imports '{imp}'")
    assert violations == [], f"Direct actions.* imports found in core/agent/: {violations}"


def test_agents_still_have_no_direct_provider_sdk_imports():
    forbidden = {"google", "google.genai", "openai", "anthropic", "ollama"}
    violations = []
    for py_file in AGENT_DIR.glob("*.py"):
        for imp in _all_imports(py_file):
            if imp.split(".")[0] in forbidden or imp in forbidden:
                violations.append(f"{py_file.name}: imports '{imp}'")
    assert violations == [], f"Direct provider SDK imports found: {violations}"


def test_only_one_tool_executor_class_exists():
    """spec Part 34/18: exactly one canonical ToolExecutor — no
    AgentToolExecutor/DeveloperToolExecutor-style duplicate anywhere."""
    violations = []
    for search_dir in (AGENT_DIR, TOOLS_DIR):
        for py_file in search_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and "ToolExecutor" in node.name:
                    violations.append(f"{py_file.relative_to(REPO_ROOT)}: defines class {node.name}")
    assert len(violations) == 1, f"Expected exactly one ToolExecutor class, found: {violations}"
    assert "core/tools/executor.py" in violations[0]


def test_tool_executor_consults_policy_engine():
    src = (TOOLS_DIR / "executor.py").read_text(encoding="utf-8")
    assert "PolicyDecision" in src
    assert "_evaluate_policy" in src
    assert "get_default_policy_engine" in src or "policy_engine" in src


def test_agents_do_not_construct_a_second_policy_engine():
    violations = []
    for py_file in AGENT_DIR.glob("*.py"):
        src = py_file.read_text(encoding="utf-8")
        if "class PolicyEngine" in src or "PolicyDecision.ALLOW" in src or "PolicyDecision.DENY" in src:
            violations.append(py_file.name)
    assert violations == [], f"core/agent/ appears to implement its own policy decisions: {violations}"


def test_no_direct_exec_eval_in_agent_or_policy_layers():
    violations = []
    for search_dir in (AGENT_DIR, REPO_ROOT / "core" / "policy"):
        for py_file in search_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in ("exec", "eval"):
                        violations.append(f"{py_file.relative_to(REPO_ROOT)}: calls {node.func.id}()")
    assert violations == [], f"Dangerous direct execution found outside sandbox/tool layers: {violations}"


def test_sandbox_never_uses_shell_true_for_generated_commands():
    """spec Part 33. Checked via AST keyword-argument inspection (not raw
    text search) since the module docstrings legitimately mention
    'shell=True' by name while explaining why it's avoided."""
    for filename in ("docker.py", "command.py"):
        path = REPO_ROOT / "core" / "sandbox" / filename
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        assert False, f"{filename} passes shell=True to a real call"


def test_desktop_exec_is_documented_as_not_a_security_boundary():
    desktop_src = (REPO_ROOT / "actions" / "desktop.py").read_text(encoding="utf-8")
    definitions_src = (REPO_ROOT / "core" / "tools" / "definitions.py").read_text(encoding="utf-8")
    assert "exec(" in desktop_src
    assert ("not a security boundary" in definitions_src.lower()
            or "not treated as a security boundary" in definitions_src.lower())


def test_dev_agent_run_project_routes_through_sandbox_manager():
    src = (REPO_ROOT / "actions" / "dev_agent.py").read_text(encoding="utf-8")
    assert "sandbox_manager" in src
    assert "execute_command_in_dir" in src


def test_dev_agent_tool_passes_default_sandbox_manager():
    src = (TOOLS_DIR / "definitions.py").read_text(encoding="utf-8")
    assert "get_default_sandbox_manager" in src


def test_browser_control_defaults_to_isolated_profile():
    src = (REPO_ROOT / "actions" / "browser_control.py").read_text(encoding="utf-8")
    assert "use_real_profile" in src
