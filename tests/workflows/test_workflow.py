import asyncio
import time
import pytest
from pathlib import Path

from core.workflows.models import (
    WorkflowDefinition, WorkflowNode, StepType, WorkflowState,
    WorkflowRunStatus, WorkflowRun, WorkflowStepRun
)
from core.workflows.engine import WorkflowEngine
from core.workflows.worker import WorkflowWorker
from core.workflows.store import WorkflowStore
from core.workflows.effects import EffectBoundary

@pytest.fixture
def store(tmp_path):
    return WorkflowStore(tmp_path / "workflows.db")

@pytest.fixture
def engine(store):
    return WorkflowEngine(store)

@pytest.fixture
def effect_boundary():
    # Mock effect boundary for testing
    class MockBoundary(EffectBoundary):
        async def execute_tool(self, tool_name, args, run_id, step_id, token):
            from core.tools.results import ToolResult
            if tool_name == "fail_tool":
                return ToolResult.fail(tool_name, error="Simulated failure")
            return ToolResult.ok(tool_name=tool_name, data=f"Mocked tool {tool_name}")
            
        async def execute_agent_task(self, goal, run_id, step_id, token):
            from core.agent.task import Task, TaskStatus
            task = Task(goal=goal)
            task.set_status(TaskStatus.COMPLETED)
            return task
            
    return MockBoundary()

@pytest.fixture
async def worker(store, engine, effect_boundary):
    w = WorkflowWorker(store, engine, effect_boundary, poll_interval_sec=0.1)
    w.start()
    yield w
    await w.stop()

def test_workflow_definition_validation(engine):
    with pytest.raises(ValueError, match="at least one node"):
        defn = WorkflowDefinition(
            id="def1", version=1, name="empty", state=WorkflowState.DRAFT,
            nodes={}, start_node_id="node1"
        )
        engine.register_definition(defn)

    with pytest.raises(ValueError, match="Start node node1 not found"):
        defn = WorkflowDefinition(
            id="def2", version=1, name="bad_start", state=WorkflowState.DRAFT,
            nodes={"node2": WorkflowNode(id="node2", type=StepType.TOOL, name="t")},
            start_node_id="node1"
        )
        engine.register_definition(defn)

@pytest.mark.asyncio
async def test_sequential_execution(engine, store, worker):
    # A -> B -> End
    defn = WorkflowDefinition(
        id="seq_flow", version=1, name="Sequential", state=WorkflowState.ACTIVE,
        nodes={
            "A": WorkflowNode(id="A", type=StepType.TOOL, name="tool_a", config={"tool_name": "test"}, next_nodes=["B"]),
            "B": WorkflowNode(id="B", type=StepType.TOOL, name="tool_b", config={"tool_name": "test"}, next_nodes=[])
        },
        start_node_id="A"
    )
    engine.register_definition(defn)
    
    run = engine.start_run("seq_flow")
    
    # Wait for completion
    timeout = time.time() + 5.0
    while time.time() < timeout:
        r = store.get_run(run.id)
        if r.status in (WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.FAILED):
            break
        await asyncio.sleep(0.1)
        
    r = store.get_run(run.id)
    assert r.status == WorkflowRunStatus.SUCCEEDED
    assert r.current_node_id is None # finishes at None
    
    steps = store._conn.execute("SELECT node_id, status FROM workflow_step_runs WHERE run_id = ? ORDER BY started_at", (run.id,)).fetchall()
    assert len(steps) == 2
    assert steps[0][0] == "A"
    assert steps[1][0] == "B"

@pytest.mark.asyncio
async def test_conditional_branching(engine, store, worker):
    defn = WorkflowDefinition(
        id="cond_flow", version=1, name="Conditional", state=WorkflowState.ACTIVE,
        nodes={
            "A": WorkflowNode(id="A", type=StepType.CONDITION, name="cond", config={
                "expression": "value == 42",
                "true_node": "B",
                "false_node": "C"
            }),
            "B": WorkflowNode(id="B", type=StepType.TOOL, name="true_path", config={"tool_name": "test"}, next_nodes=[]),
            "C": WorkflowNode(id="C", type=StepType.TOOL, name="false_path", config={"tool_name": "test"}, next_nodes=[])
        },
        start_node_id="A"
    )
    engine.register_definition(defn)
    
    # Test True path
    run1 = engine.start_run("cond_flow", context={"value": 42})
    
    timeout = time.time() + 5.0
    while time.time() < timeout:
        r = store.get_run(run1.id)
        if r.status in (WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.FAILED):
            break
        await asyncio.sleep(0.1)
        
    steps = store._conn.execute("SELECT node_id FROM workflow_step_runs WHERE run_id = ?", (run1.id,)).fetchall()
    node_ids = [s[0] for s in steps]
    assert "A" in node_ids
    assert "B" in node_ids
    assert "C" not in node_ids
    
    # Test False path
    run2 = engine.start_run("cond_flow", context={"value": 99})
    timeout = time.time() + 5.0
    while time.time() < timeout:
        r = store.get_run(run2.id)
        if r.status in (WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.FAILED):
            break
        await asyncio.sleep(0.1)
        
    steps = store._conn.execute("SELECT node_id FROM workflow_step_runs WHERE run_id = ?", (run2.id,)).fetchall()
    node_ids = [s[0] for s in steps]
    assert "A" in node_ids
    assert "C" in node_ids
    assert "B" not in node_ids

@pytest.mark.asyncio
async def test_cancellation(engine, store, worker):
    # Workflow with a WAIT node (or just catch it before it starts)
    # Since we can't easily pause without a real sleep in the mock, we will pause the worker before starting
    pass # we can test basic cancellation state transition
    
    defn = WorkflowDefinition(
        id="cancel_flow", version=1, name="Cancel", state=WorkflowState.ACTIVE,
        nodes={"A": WorkflowNode(id="A", type=StepType.TOOL, name="t", config={"tool_name": "test"})},
        start_node_id="A"
    )
    engine.register_definition(defn)
    
    run = engine.start_run("cancel_flow")
    engine.cancel_run(run.id)
    
    r = store.get_run(run.id)
    assert r.status == WorkflowRunStatus.CANCELLING

@pytest.mark.asyncio
async def test_retry_on_failure(engine, store, worker):
    defn = WorkflowDefinition(
        id="retry_flow", version=1, name="Retry", state=WorkflowState.ACTIVE,
        nodes={
            "A": WorkflowNode(id="A", type=StepType.TOOL, name="fail_tool", config={"tool_name": "fail_tool"}, next_nodes=[])
        },
        start_node_id="A"
    )
    engine.register_definition(defn)
    
    run = engine.start_run("retry_flow")
    run.max_attempts = 2
    store.save_run(run)
    
    timeout = time.time() + 5.0
    while time.time() < timeout:
        r = store.get_run(run.id)
        if r.status in (WorkflowRunStatus.FAILED, WorkflowRunStatus.SUCCEEDED):
            break
        # Mock time wait for backoff
        if r.status == WorkflowRunStatus.RETRYING:
            r.locked_until = time.time() - 1
            store.save_run(r)
        await asyncio.sleep(0.1)
        
    r = store.get_run(run.id)
    assert r.status == WorkflowRunStatus.FAILED
    assert r.attempt == 3 # 1 original + 2 retries
