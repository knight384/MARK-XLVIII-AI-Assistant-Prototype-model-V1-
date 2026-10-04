"""tests/memory/test_projects.py"""
from __future__ import annotations

from core.memory.projects import ProjectMemory, derive_project_id


def test_set_and_get_facts(durable_store):
    pm = ProjectMemory(durable_store)
    pm.set_fact("proj-1", "tech_stack", "Python + FastAPI")
    facts = pm.get_facts("proj-1")
    assert len(facts) == 1
    assert facts[0].content == "Python + FastAPI"


def test_get_facts_filtered_by_field(durable_store):
    pm = ProjectMemory(durable_store)
    pm.set_fact("proj-1", "tech_stack", "Python")
    pm.set_fact("proj-1", "known_issue", "flaky test")
    facts = pm.get_facts("proj-1", field="tech_stack")
    assert len(facts) == 1
    assert facts[0].content == "Python"


def test_project_isolation(durable_store):
    """Different projects remain isolated (spec Part 50 acceptance criteria)."""
    pm = ProjectMemory(durable_store)
    pm.set_fact("proj-a", "tech_stack", "Python")
    pm.set_fact("proj-b", "tech_stack", "Go")
    assert pm.get_facts("proj-a")[0].content == "Python"
    assert pm.get_facts("proj-b")[0].content == "Go"
    assert len(pm.get_facts("proj-a")) == 1


def test_forget_project(durable_store):
    pm = ProjectMemory(durable_store)
    pm.set_fact("proj-1", "a", "x")
    pm.set_fact("proj-1", "b", "y")
    removed = pm.forget_project("proj-1")
    assert removed == 2
    assert pm.get_facts("proj-1") == []


def test_project_namespace_is_scoped(durable_store):
    pm = ProjectMemory(durable_store)
    record = pm.set_fact("proj-1", "field", "value")
    assert record.namespace == "project:proj-1"


# -- project identity derivation (spec Part 17) --------------------------

def test_explicit_id_wins(tmp_path):
    assert derive_project_id(tmp_path, explicit_id="my-explicit-id") == "my-explicit-id"


def test_path_based_fallback_is_stable(tmp_path):
    id1 = derive_project_id(tmp_path)
    id2 = derive_project_id(tmp_path)
    assert id1 == id2  # same path -> same id, deterministically


def test_different_paths_yield_different_ids(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    assert derive_project_id(dir_a) != derive_project_id(dir_b)


def test_git_remote_based_id_when_available(tmp_path):
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/x/y.git"], cwd=repo, check=True)
    project_id = derive_project_id(repo)
    assert project_id.startswith("git:")

    # Same remote from a different clone path -> same id (stable across clones).
    repo2 = tmp_path / "repo_clone"
    repo2.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo2, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/x/y.git"], cwd=repo2, check=True)
    assert derive_project_id(repo2) == project_id
