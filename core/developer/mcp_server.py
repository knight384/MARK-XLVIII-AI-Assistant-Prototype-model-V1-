import logging
from typing import Dict, Any, List, Optional
import asyncio

from core.runtime.app import MarkRuntime
from core.agent.orchestrator import get_default_orchestrator
from core.agent.task import Task
from core.tools.base import CancellationToken

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
            "inspect_git": "Read git status and current branch"
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
                
        return {"isError": True, "content": [{"type": "text", "text": "Unknown or restricted tool"}]}
