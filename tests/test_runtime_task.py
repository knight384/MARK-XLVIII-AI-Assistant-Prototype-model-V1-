import pytest
import asyncio
from core.agent.orchestrator import Orchestrator
from core.agent.task import TaskStatus

@pytest.mark.asyncio
async def test_uncaught_orchestration_exception():
    class CrashingPlanner:
        async def plan(self, *args, **kwargs):
            raise RuntimeError("Unexpected planner crash")
            
    orchestrator = Orchestrator(planner=CrashingPlanner())
    
    task = await orchestrator.run_task("do something")
    
    assert task.status == TaskStatus.FAILED
    assert any("Uncaught orchestration exception" in e for e in task.errors)
