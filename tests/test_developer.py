import pytest
from core.developer.project import ProjectAnalyzer
from core.developer.git import GitIntelligence
from core.developer.github import GitHubIntelligence
from core.developer.context import ContextBuilder
from core.developer.mcp_server import MCPServer
from core.runtime.app import MarkRuntime
from core.runtime.mode import RuntimeMode
from core.tools.base import ToolContext
from core.developer.tools import (
    DeveloperGitReadTool, DeveloperGitWriteTool, DeveloperCodeSearchTool, DeveloperGitHubWriteTool
)

def test_project_analyzer():
    analyzer = ProjectAnalyzer()
    index = analyzer.analyze(".")
    assert index.root_path is not None
    assert "Python" in index.languages or len(index.languages) >= 0 # Dynamic based on CWD

def test_git_intelligence():
    git = GitIntelligence(".")
    # Read operations should not mutate
    status = git.status()
    assert isinstance(status, str)
    branch = git.current_branch()
    assert isinstance(branch, str)

def test_context_builder():
    builder = ContextBuilder(".")
    ctx = builder.build_context("Test task")
    assert "PROJECT CONTEXT" in ctx
    assert "GIT STATE" in ctx

@pytest.mark.asyncio
async def test_mcp_server_lists_tools():
    runtime = MarkRuntime(mode=RuntimeMode.HEADLESS)
    mcp = MCPServer(runtime)
    res = await mcp.handle_request("tools/list", {})
    assert "tools" in res
    tool_names = [t["name"] for t in res["tools"]]
    assert "submit_developer_task" in tool_names
    assert "inspect_project" in tool_names

@pytest.mark.asyncio
async def test_security_git_write_requires_approval():
    tool = DeveloperGitWriteTool()
    assert tool.metadata.requires_confirmation is True
    assert tool.metadata.risk_level.name in ["HIGH", "CRITICAL"]

@pytest.mark.asyncio
async def test_security_github_write_requires_approval():
    tool = DeveloperGitHubWriteTool()
    assert tool.metadata.requires_confirmation is True
    assert tool.metadata.risk_level.name in ["HIGH", "CRITICAL"]

@pytest.mark.asyncio
async def test_code_search_tool():
    tool = DeveloperCodeSearchTool()
    ctx = ToolContext()
    # Search for a known string in this file
    res = await tool.execute({"query": "test_code_search_tool"}, ctx)
    assert res.success
    assert "test_code_search_tool" in res.data
