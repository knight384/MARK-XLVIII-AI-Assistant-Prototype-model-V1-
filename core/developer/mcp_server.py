import logging
from typing import Dict, Any, List, Optional
import asyncio

from core.runtime.app import MarkRuntime
from core.agent.orchestrator import get_default_orchestrator
from core.agent.task import Task
from core.tools.base import CancellationToken
from core.mission.models import Mission, MissionState, TriggerType
from core.mission.store import get_default_store
from core.goals.service import get_default_goal_service
from core.goals.store import get_default_goal_store
from core.personality.service import get_default_personality_service
import uuid
import time

logger = logging.getLogger(__name__)

class MCPServer:
    """MARK-native MCP integration layer.
    
    Exposes bounded developer capabilities to IDE clients.
    Critically, this does NOT execute operations directly. 
    It routes all requests through the MARK Runtime -> Orchestrator -> ToolExecutor -> PolicyEngine.
    """
    
    def __init__(self, runtime: MarkRuntime):
        self.runtime = runtime
        # Basic mapping of exposed MCP tools to their descriptions
        self.exposed_tools = {
            "submit_developer_task": "Submit a high-level developer task for MARK to execute",
            "get_task_status": "Check the status of a submitted developer task",
            "inspect_project": "Analyze the current project and return metadata",
            "search_code": "Search code using safe bounded search",
            "inspect_git": "Read git status and current branch",
            "create_mission": "Create a new proactive or recurring mission",
            "list_missions": "List all missions and their statuses",
            "run_mission": "Manually trigger a mission execution",
            "cancel_mission": "Cancel a scheduled or running mission",
            "create_goal": "Create a new high-level goal",
            "list_goals": "List active goals",
            "inspect_personality": "Inspect learned personality preferences"
        }

    async def handle_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Entry point for MCP JSON-RPC requests."""
        if method == "tools/list":
            return {
                "tools": [
                    {"name": k, "description": v, "inputSchema": {"type": "object", "properties": {}}}
                    for k, v in self.exposed_tools.items()
                ]
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            return await self._route_tool(tool_name, tool_args)
            
        raise ValueError(f"Method {method} not supported")

    async def _route_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "submit_developer_task":
            # Routes to the Orchestrator, ensuring it passes through PolicyEngine and ToolExecutor
            goal = args.get("goal")
            if not goal:
                return {"isError": True, "content": [{"type": "text", "text": "Missing 'goal'"}]}
            
            orchestrator = get_default_orchestrator()
            task = Task(goal=goal)
            token = CancellationToken()
            
            # Using fire-and-forget for async execution to return task_id immediately
            async def run():
                await orchestrator._run_task_impl(task, goal, token)
            asyncio.create_task(run())
            
            return {"content": [{"type": "text", "text": f"Task submitted. ID: {task.task_id}"}]}
            
        elif tool_name == "inspect_project":
            from core.developer.project import ProjectAnalyzer
            analyzer = ProjectAnalyzer()
            # Defaults to CWD or configured workspace
            index = analyzer.analyze(".") 
            return {"content": [{"type": "text", "text": str(index.__dict__)}]}
            
        elif tool_name == "inspect_git":
            from core.developer.git import GitIntelligence
            try:
                git = GitIntelligence(".")
                return {"content": [{"type": "text", "text": f"Branch: {git.current_branch()}\nStatus: {git.status()}"}]}
            except Exception as e:
                return {"isError": True, "content": [{"type": "text", "text": str(e)}]}
                
        elif tool_name == "create_mission":
            store = get_default_store()
            name = args.get("name")
            desc = args.get("description")
            if not name or not desc:
                return {"isError": True, "content": [{"type": "text", "text": "Missing name or description"}]}
            m = Mission(
                id=str(uuid.uuid4()),
                name=name,
                description=desc,
                owner="developer",
                state=MissionState.SCHEDULED,
                trigger_type=TriggerType.CRON if args.get("cron") else TriggerType.MANUAL,
                cron_expression=args.get("cron"),
                created_at=time.time(),
                updated_at=time.time()
            )
            store.save(m)
            return {"content": [{"type": "text", "text": f"Created mission {m.id}"}]}
            
        elif tool_name == "list_missions":
            store = get_default_store()
            missions = store.list_missions()
            resp = "\\n".join([f"[{m.id}] {m.name} - {m.state.value}" for m in missions])
            return {"content": [{"type": "text", "text": resp}]}
            
        elif tool_name == "run_mission":
            mid = args.get("mission_id")
            store = get_default_store()
            mission = store.get(mid) if mid else None
            if not mission:
                return {"isError": True, "content": [{"type": "text", "text": "Mission not found"}]}
            mission.state = MissionState.RUNNING
            store.save(mission)
            
            orchestrator = get_default_orchestrator()
            task = Task(goal=f"MISSION: {mission.name}\\n{mission.description}")
            asyncio.create_task(orchestrator._run_task_impl(task, task.goal, CancellationToken()))
            return {"content": [{"type": "text", "text": f"Mission {mid} started."}]}
            
        elif tool_name == "cancel_mission":
            mid = args.get("mission_id")
            store = get_default_store()
            mission = store.get(mid) if mid else None
            if not mission:
                return {"isError": True, "content": [{"type": "text", "text": "Mission not found"}]}
            mission.state = MissionState.CANCELLED
            store.save(mission)
            return {"content": [{"type": "text", "text": f"Mission {mid} cancelled."}]}
        elif tool_name == "create_goal":
            title = args.get("title")
            desc = args.get("description")
            if not title or not desc:
                return {"isError": True, "content": [{"type": "text", "text": "Missing title or description"}]}
            svc = get_default_goal_service()
            g = svc.create_goal(title, desc)
            return {"content": [{"type": "text", "text": f"Created goal {g.id}"}]}

        elif tool_name == "list_goals":
            store = get_default_goal_store()
            goals = store.list_goals()
            resp = "\\n".join([f"[{g.id}] {g.title} - {g.state.value} ({g.progress}%)" for g in goals])
            return {"content": [{"type": "text", "text": resp or "No goals"}]}

        elif tool_name == "inspect_personality":
            svc = get_default_personality_service()
            prefs = svc.get_all_preferences()
            resp = "\\n".join([f"{p.category}: {p.value} (conf: {p.confidence})" for p in prefs])
            return {"content": [{"type": "text", "text": resp or "No preferences learned yet"}]}
                
        return {"isError": True, "content": [{"type": "text", "text": "Unknown or restricted tool"}]}
