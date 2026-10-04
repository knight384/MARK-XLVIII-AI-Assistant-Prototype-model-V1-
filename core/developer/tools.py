from typing import Any
from core.tools.base import Tool, ToolContext, ToolResult
from core.tools.schemas import ToolSchema, ParamSchema
from core.tools.metadata import ToolMetadata, RiskLevel
from core.runtime.events import EventBus, Event, EventType

from core.developer.project import ProjectAnalyzer
from core.developer.git import GitIntelligence
from core.developer.github import GitHubIntelligence

class DeveloperProjectInspectTool(Tool):
    name = "developer_project_inspect"
    description = "Inspect the project repository to identify languages, structure, and test commands."
    schema = ToolSchema(
        parameters=(
            ParamSchema(name="path", type="string", description="Path to inspect, defaults to current directory"),
        )
    )
    metadata = ToolMetadata(
        category="developer",
        risk_level=RiskLevel.LOW,
        requires_confirmation=False,
        requires_sandbox=False
    )
    
    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        path = args.get("path", ".")
        analyzer = ProjectAnalyzer()
        try:
            index = analyzer.analyze(path)
            return ToolResult.ok(self.name, data=str(index.__dict__))
        except Exception as e:
            return ToolResult.fail(self.name, error=f"Project inspection failed: {e}")

class DeveloperGitReadTool(Tool):
    name = "developer_git_read"
    description = "Perform read-only Git operations (status, diff, log)."
    schema = ToolSchema(
        parameters=(
            ParamSchema(name="operation", type="string", required=True, enum=("status", "diff", "log", "branch")),
        )
    )
    metadata = ToolMetadata(
        category="developer",
        risk_level=RiskLevel.LOW,
        requires_confirmation=False,
        requires_sandbox=False
    )
    
    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        op = args["operation"]
        EventBus.publish(Event(type=EventType.INFO, source="developer_git_read", payload={"operation": op}))
        git = GitIntelligence(".")
        try:
            if op == "status":
                res = git.status()
            elif op == "diff":
                res = git.diff()
            elif op == "log":
                res = git.log()
            elif op == "branch":
                res = git.current_branch()
            else:
                return ToolResult.fail(self.name, error="Unknown operation")
            EventBus.publish(Event(type=EventType.INFO, source="developer_git_read", payload={"status": "completed", "operation": op}))
            return ToolResult.ok(self.name, data=res)
        except Exception as e:
            EventBus.publish(Event(type=EventType.ERROR, source="developer_git_read", payload={"error": str(e)}))
            return ToolResult.fail(self.name, error=str(e))

class DeveloperGitWriteTool(Tool):
    name = "developer_git_write"
    description = "Perform mutating Git operations like commit or push."
    schema = ToolSchema(
        parameters=(
            ParamSchema(name="operation", type="string", required=True, enum=("commit", "push")),
            ParamSchema(name="message", type="string"),
        )
    )
    metadata = ToolMetadata(
        category="developer",
        risk_level=RiskLevel.HIGH,
        requires_confirmation=True, # Critical safety invariant
        requires_sandbox=False
    )
    
    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        op = args["operation"]
        import subprocess
        try:
            if op == "commit":
                msg = args.get("message", "Auto-commit")
                # Requires approval by policy engine before executing
                res = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True, timeout=10)
                return ToolResult.ok(self.name, data=res.stdout) if res.returncode == 0 else ToolResult.fail(self.name, error=res.stderr)
            elif op == "push":
                res = subprocess.run(["git", "push"], capture_output=True, text=True, timeout=20)
                return ToolResult.ok(self.name, data=res.stdout) if res.returncode == 0 else ToolResult.fail(self.name, error=res.stderr)
        except Exception as e:
            return ToolResult.fail(self.name, error=str(e))
            
class DeveloperGitHubReadTool(Tool):
    name = "developer_github_read"
    description = "Read GitHub issues or pull requests."
    schema = ToolSchema(
        parameters=(
            ParamSchema(name="repo", type="string", required=True),
            ParamSchema(name="operation", type="string", required=True, enum=("issue", "pr", "list")),
            ParamSchema(name="number", type="integer"),
        )
    )
    metadata = ToolMetadata(
        category="developer",
        risk_level=RiskLevel.LOW,
        requires_confirmation=False,
        requires_sandbox=False
    )
    
    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        gh = GitHubIntelligence(args["repo"])
        op = args["operation"]
        try:
            if op == "list":
                return ToolResult.ok(self.name, data=str(gh.list_issues()))
            num = args.get("number")
            if not num:
                return ToolResult.fail(self.name, error="number required")
            if op == "issue":
                return ToolResult.ok(self.name, data=str(gh.get_issue(num)))
            elif op == "pr":
                return ToolResult.ok(self.name, data=str(gh.get_pull_request(num)))
        except Exception as e:
            return ToolResult.fail(self.name, error=str(e))

class DeveloperGitHubWriteTool(Tool):
    name = "developer_github_write"
    description = "Write GitHub issues or pull requests (requires approval)."
    schema = ToolSchema(
        parameters=(
            ParamSchema(name="repo", type="string", required=True),
            ParamSchema(name="operation", type="string", required=True, enum=("create_issue", "comment_issue")),
            ParamSchema(name="title", type="string"),
            ParamSchema(name="body", type="string"),
        )
    )
    metadata = ToolMetadata(
        category="developer",
        risk_level=RiskLevel.HIGH,
        requires_confirmation=True,
        requires_sandbox=False
    )
    
    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        return ToolResult.fail(self.name, error="GitHub Write API mutating operations must use requests POST, deferred for live token.")

class DeveloperCodeSearchTool(Tool):
    name = "developer_code_search"
    description = "Search codebase for text or symbols safely."
    schema = ToolSchema(
        parameters=(
            ParamSchema(name="query", type="string", required=True),
        )
    )
    metadata = ToolMetadata(
        category="developer",
        risk_level=RiskLevel.LOW,
        requires_confirmation=False,
        requires_sandbox=False
    )
    
    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        query = args["query"]
        import os
        results = []
        for root, dirs, files in os.walk("."):
            if any(part in root for part in [".git", "node_modules", "venv", "__pycache__"]):
                continue
            for file in files:
                if file.endswith((".py", ".ts", ".js", ".json", ".md", ".txt", ".java", ".go")):
                    path = os.path.join(root, file)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            for i, line in enumerate(f):
                                if query in line:
                                    results.append(f"{path}:{i+1}: {line.strip()}")
                                    if len(results) >= 50: # Bounded search
                                        results.append("... [Search truncated at 50 results]")
                                        return ToolResult.ok(self.name, data="\n".join(results))
                    except Exception:
                        pass
        return ToolResult.ok(self.name, data="\n".join(results) if results else "No results found.")
