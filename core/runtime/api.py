from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import asyncio

from core.runtime.app import MarkRuntime
from core.agent.orchestrator import get_default_orchestrator
from core.agent.task import Task, TaskStatus
from core.tools.base import CancellationToken, CancelReason

app = FastAPI(title="MARK XLVIII Runtime API", version="7.0")
_runtime: Optional[MarkRuntime] = None
_tasks: Dict[str, Task] = {}
_tokens: Dict[str, CancellationToken] = {}

def set_runtime(runtime: MarkRuntime):
    global _runtime
    _runtime = runtime

@app.get("/health")
async def health():
    if not _runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    return {"status": "ok", "mode": _runtime.mode.name}

@app.get("/identity")
async def identity():
    if not _runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    return {"identity": _runtime.identity.runtime_id, "mode": _runtime.mode.name}

@app.get("/capabilities")
async def capabilities():
    caps = []
    # local capabilities
    from core.tools import get_default_registry
    from core.runtime.providers import LocalCapabilityProvider
    local = LocalCapabilityProvider(get_default_registry())
    caps.extend([c.__dict__ for c in await local.discover()])
    return {"capabilities": caps}

@app.get("/models")
async def models():
    from core.llm.gateway import get_default_gateway
    gw = get_default_gateway()
    return {"providers": gw.health_check_all()}

class TaskRequest(BaseModel):
    goal: str

@app.post("/tasks")
async def submit_task(req: TaskRequest):
    orchestrator = get_default_orchestrator()
    token = CancellationToken()
    # Create the task synchronously to get its ID before starting execution
    task = Task(goal=req.goal)
    _tasks[task.task_id] = task
    _tokens[task.task_id] = token
    
    async def run():
        await orchestrator._run_task_impl(task, req.goal, token)
        
    asyncio.create_task(run())
    return {"task_id": task.task_id, "status": task.status.value}

@app.get("/tasks/{task_id}")
async def task_status(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = _tasks[task_id]
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "summary": task.summary(),
        "errors": task.errors
    }

@app.get("/tasks/{task_id}/result")
async def task_result(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = _tasks[task_id]
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "observations": [o.__dict__ for o in task.observations]
    }

@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    if task_id not in _tokens:
        raise HTTPException(status_code=404, detail="Task not found")
    _tokens[task_id].cancel(reason=CancelReason.USER_REQUEST)
    return {"status": "cancelling"}

@app.get("/events")
async def get_events():
    return {"status": "Event streaming not implemented via polling. Attach via WebSocket."}
