"""MCP client (Phase 17) - the ONLY thing in this backend allowed to talk to
the standalone MCP server (../mcp-server). Wraps the official MCP Python
SDK's Streamable HTTP client (mcp==2.0.0, same version the server uses -
verified live: connect, initialize, list_tools, call_tool all confirmed
against the real running Phase 16 server before this was written).

Nothing else in the app should import `mcp` directly or know the server's
URL - app/langgraph/nodes/agent_node.py is the only caller, and it only ever
sees this class's plain dict-based methods, never the MCP SDK's own types.
This is what keeps weather/email logic entirely inside the MCP server (Phase
17 doc section 3): this client can only discover and invoke tools the
server chooses to expose, never call a weather/email API directly itself.

A fresh connection is opened and closed for every list_tools()/call_tool()
call rather than holding one long-lived session open across the process
lifetime - simpler and more robust (no stale-connection/reconnect logic to
get wrong) at the cost of a small per-call latency, acceptable for a
portfolio project's traffic. Tool schemas ARE cached in memory after the
first successful discovery, so repeated turns don't re-fetch them.
"""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from app.mcp.errors import MCPToolExecutionError, MCPUnavailableError
from app.services.model_service import ToolSpec

logger = logging.getLogger(__name__)


class MCPClientService:
    def __init__(self, server_url: str, *, timeout_seconds: float = 15.0) -> None:
        self._server_url = server_url
        self._timeout_seconds = timeout_seconds
        self._tools_cache: list[ToolSpec] | None = None

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        # The MCP SDK vendors its own httpx fork (a separate `httpx2` PyPI
        # package, NOT this app's regular `httpx`) for its transport layer -
        # confirmed live that `httpx2.AsyncClient is not httpx.AsyncClient`,
        # so a plain `httpx.AsyncClient` passed as `http_client=` would be
        # the wrong type. create_mcp_http_client() is the SDK's own factory
        # for building a correctly-typed client with a custom timeout.
        http_client = create_mcp_http_client(timeout=self._timeout_seconds)
        try:
            async with streamable_http_client(self._server_url, http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        except MCPUnavailableError:
            raise
        except Exception as exc:
            logger.exception("Failed to connect to MCP server at %s", self._server_url)
            raise MCPUnavailableError(
                f"Could not reach the MCP server at {self._server_url}."
            ) from exc
        finally:
            await http_client.aclose()

    async def list_tools(self, *, refresh: bool = False) -> list[ToolSpec]:
        """Tool discovery (Phase 17 doc section 4) - never hardcoded; always
        asks the server what it currently exposes. Cached after the first
        successful call so the model's per-turn context doesn't pay a
        network round trip just to re-learn schemas that haven't changed."""
        if self._tools_cache is not None and not refresh:
            return self._tools_cache

        async with self._session() as session:
            result = await session.list_tools()

        self._tools_cache = [
            {"name": tool.name, "description": tool.description or "", "parameters": tool.input_schema}
            for tool in result.tools
        ]
        return self._tools_cache

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Executes one tool call and returns its structured result as a
        plain dict. Raises MCPToolExecutionError (with the tool's own clean
        message) if the tool itself reported failure, or MCPUnavailableError
        if the server couldn't be reached at all - callers never see a raw
        MCP SDK exception or stack trace."""
        async with self._session() as session:
            try:
                result = await session.call_tool(
                    name, arguments, read_timeout_seconds=self._timeout_seconds
                )
            except Exception as exc:
                logger.exception("MCP call_tool(%s) transport failure", name)
                raise MCPUnavailableError(f"Failed to call MCP tool {name!r}.") from exc

        if result.is_error:
            message = "Tool call failed."
            if result.content:
                first = result.content[0]
                message = getattr(first, "text", None) or message
            logger.warning("MCP tool %s reported an error: %s", name, message)
            raise MCPToolExecutionError(message)

        if result.structured_content is not None:
            return result.structured_content

        # Fallback for a tool with no structured output schema - shouldn't
        # happen for the tools this app actually calls (all declare
        # structured Pydantic results server-side), but degrade gracefully
        # rather than crash if it ever does.
        text = result.content[0].text if result.content and hasattr(result.content[0], "text") else ""
        return {"result": text}
