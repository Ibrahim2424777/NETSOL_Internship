"""MCP client-layer error types (Phase 17 doc section 21).

Distinguishes "couldn't reach/talk to the MCP server at all" from "the
server answered, but the specific tool call itself failed" - agent_node.py
treats them slightly differently (the former is worth a distinct
user-facing message; the latter's message usually already IS a clean,
tool-specific explanation - see mcp-server's own error handling, Phase 16
doc section 9)."""


class MCPError(Exception):
    """Base class for all MCP-client-layer failures."""


class MCPUnavailableError(MCPError):
    """Could not connect to, or communicate with, the MCP server at all -
    connection refused, DNS failure, timeout establishing the session, etc."""


class MCPToolExecutionError(MCPError):
    """The MCP server was reached and responded, but the tool call itself
    reported isError=true - message is the tool's own explanation (e.g.
    "No location found matching 'Zzz'."), already clean and safe to show
    the model/user as-is, never a raw stack trace."""
