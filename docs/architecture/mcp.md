# MCP (Model Context Protocol) Architecture

MARK XLVIII exposes Developer Intelligence tools through an MCP facade for IDE integration.

## Trust Model
MCP requests DO NOT bypass execution authority. The MCP server translates RPC JSON requests into safe developer tool actions routed into the `Task` abstraction and executed under `ToolExecutor` and `PolicyEngine` enforcement.

## Exposed Capabilities
- `submit_developer_task`: Submit autonomous tasks to MARK.
- `inspect_project`: Safe, bounded project analysis.
- `search_code`: Bounded search.
- `inspect_git`: Status and branching reads.
