from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import asyncio

from core.runtime.app import MarkRuntime
from core.agent.orchestrator import get_default_orchestrator
from core.agent.task import Task, TaskStatus
from core.tools.base import CancellationToken, CancelReason
from core.mission.models import Mission, MissionState, TriggerType
from core.mission.store import get_default_store
from core.goals.service import get_default_goal_service
from core.goals.store import get_default_goal_store
from core.goals.models import GoalState
from core.personality.service import get_default_personality_service
from core.awareness.tracker import get_default_tracker
import time
import uuid

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

class MissionCreateRequest(BaseModel):
    name: str
    description: str
    owner: str = "user"
    trigger_type: str = "MANUAL"
    cron_expression: Optional[str] = None
    trigger_event: Optional[str] = None

@app.post("/missions")
async def create_mission(req: MissionCreateRequest):
    store = get_default_store()
    mission = Mission(
        id=str(uuid.uuid4()),
        name=req.name,
        description=req.description,
        owner=req.owner,
        state=MissionState.DRAFT if req.trigger_type == "MANUAL" else MissionState.SCHEDULED,
        trigger_type=TriggerType(req.trigger_type),
        created_at=time.time(),
        updated_at=time.time(),
        cron_expression=req.cron_expression,
        trigger_event=req.trigger_event
    )
    store.save(mission)
    return mission.to_dict()

@app.get("/missions")
async def list_missions(state: Optional[str] = None):
    store = get_default_store()
    st = MissionState(state) if state else None
    missions = store.list_missions(state=st)
    return [m.to_dict() for m in missions]

@app.get("/missions/{mission_id}")
async def get_mission(mission_id: str):
    store = get_default_store()
    mission = store.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission.to_dict()

@app.post("/missions/{mission_id}/run")
async def run_mission(mission_id: str):
    store = get_default_store()
    mission = store.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
        
    mission.state = MissionState.RUNNING
    mission.last_execution_at = time.time()
    store.save(mission)
    
    # Fire and forget execution to keep API responsive
    orchestrator = get_default_orchestrator()
    task = Task(goal=f"MISSION: {mission.name}\n{mission.description}")
    token = CancellationToken()
    asyncio.create_task(orchestrator._run_task_impl(task, task.goal, token))
    
    return {"status": "started", "task_id": task.task_id}

@app.post("/missions/{mission_id}/pause")
async def pause_mission(mission_id: str):
    store = get_default_store()
    mission = store.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission.state = MissionState.PAUSED
    store.save(mission)
    return {"status": "paused"}

@app.post("/missions/{mission_id}/resume")
async def resume_mission(mission_id: str):
    store = get_default_store()
    mission = store.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission.state = MissionState.SCHEDULED
    store.save(mission)
    return {"status": "resumed"}

@app.post("/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str):
    store = get_default_store()
    mission = store.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission.state = MissionState.CANCELLED
    store.save(mission)
    return {"status": "cancelled"}

@app.get("/missions/{mission_id}/history")
async def get_mission_history(mission_id: str):
    store = get_default_store()
    mission = store.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    # Stubbed history for now; in a real app this would query a mission_history table
    return {"history": [{"event": "created", "timestamp": mission.created_at}]}

class GoalCreateRequest(BaseModel):
    title: str
    description: str
    priority: int = 0

@app.post("/goals")
async def create_goal(req: GoalCreateRequest):
    svc = get_default_goal_service()
    goal = svc.create_goal(title=req.title, description=req.description, priority=req.priority)
    return goal.to_dict()

@app.get("/goals")
async def list_goals(state: Optional[str] = None):
    store = get_default_goal_store()
    st = GoalState(state) if state else None
    return [g.to_dict() for g in store.list_goals(state=st)]

@app.get("/goals/{goal_id}")
async def get_goal(goal_id: str):
    store = get_default_goal_store()
    g = store.get(goal_id)
    if not g:
        raise HTTPException(status_code=404, detail="Goal not found")
    return g.to_dict()

@app.post("/goals/{goal_id}/complete")
async def complete_goal(goal_id: str):
    svc = get_default_goal_service()
    if not svc.complete_goal(goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"status": "completed"}

@app.get("/awareness/signals")
async def get_awareness_signals():
    tracker = get_default_tracker()
    return {"signals": [s.to_dict() for s in tracker.get_recent_signals()]}

@app.get("/personality/preferences")
async def get_personality_preferences():
    svc = get_default_personality_service()
    return {"preferences": [p.to_dict() for p in svc.get_all_preferences()]}

class LearnRequest(BaseModel):
    category: str
    value: str
    confidence: float = 0.5

@app.post("/personality/learning")
async def learn_personality(req: LearnRequest):
    svc = get_default_personality_service()
    pref = svc.learn_preference(req.category, req.value, req.confidence)
    if not pref:
        return {"status": "ignored"}
    return pref.to_dict()

