"""Runs the chat graph end-to-end for a single turn.

This is the intended entry point for the rest of the app to get an AI
response - the Messages endpoint calls run_stream(...) rather than touching
the graph or Gemini/Groq directly, so "every request passes through
LangGraph" holds by construction, not just by convention.

chat_id doubles as the LangGraph thread_id: each call passes only the new
turn's HumanMessage as input, and the checkpointer supplies everything the
model has said/heard before in that chat. Isolation between chats/users falls
out of thread_id scoping in the checkpointer itself - callers must still only
ever pass a chat_id the caller has already verified the current user owns
(see OwnedChat in app/api/deps.py); this service does not re-check ownership.

Phase 14 folded RAG retrieval into ONE graph with a router node choosing the
path per turn (see app/langgraph/graphs/chat_graph.py) - run_stream/run don't
mean "the RAG graph specifically"; which retrieval (if any) runs is an
internal decision the graph makes for each message. Phase 14.6 replaced the
"sports" route with "web_search" and made it a CALLER-supplied override
rather than something the classifier ever infers - see run_stream's
web_search parameter. Phase 18 replaced web_search's retrieval mechanism
(Groq compound-mini's autonomous search) with Tavily; the override behavior
itself is unchanged.
"""
import uuid
from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from app.langgraph.graphs.chat_graph import build_chat_graph
from app.langgraph.state import ChatState, Route, WebSearchSource
from app.mcp.client import MCPClientService
from app.rag.retriever import Retriever
from app.services.model_service import ModelService
from app.services.tavily_service import TavilySearchService
from app.services.vector_store_service import RetrievedChunk


class ChatExecutionService:
    def __init__(
        self,
        model_service: ModelService,
        tavily_service: TavilySearchService,
        retriever: Retriever,
        mcp_client: MCPClientService,
        *,
        checkpointer: BaseCheckpointSaver,
        max_history_messages: int,
        router_context_messages: int = 6,
    ) -> None:
        self._checkpointer = checkpointer
        self._graph: CompiledStateGraph = build_chat_graph(
            model_service,
            tavily_service,
            retriever,
            mcp_client,
            checkpointer=checkpointer,
            max_history_messages=max_history_messages,
            router_context_messages=router_context_messages,
        )

    async def forget_chat(self, chat_id: uuid.UUID) -> None:
        """Deletes all checkpointed state for a chat's thread_id. Must be
        called whenever a chat is deleted (see delete_chat in
        app/api/v1/endpoints/chats.py) - Postgres cascade-deletes the chat's
        rows in the `messages` table, but the checkpointer's tables have no
        foreign key relationship to them and would otherwise keep the full
        conversation indefinitely after the chat is "deleted"."""
        await self._checkpointer.adelete_thread(str(chat_id))

    def _config(self, chat_id: uuid.UUID) -> dict:
        return {"configurable": {"thread_id": str(chat_id)}}

    def _initial_state(self, user_input: str, *, web_search: bool) -> ChatState:
        return {
            "messages": [HumanMessage(content=user_input)],
            "retrieved_context": [],
            "web_search_results": [],
            "web_search_sources": [],
            "web_search_requested": web_search,
            "tool_calls_made": [],
            "route": None,
        }

    async def run(self, chat_id: uuid.UUID, user_input: str, *, web_search: bool = False) -> str:
        """Non-streaming: run the graph to completion and return the full
        response. Not used by the chat-message endpoint (which streams), but
        kept for callers that just want a single result - e.g. a future
        auto-title-generation feature."""
        result = await self._graph.ainvoke(
            self._initial_state(user_input, web_search=web_search), config=self._config(chat_id)
        )

        messages = result["messages"]
        if not messages:
            raise RuntimeError("Chat graph completed without producing a response")
        return messages[-1].content

    async def run_stream(
        self, chat_id: uuid.UUID, user_input: str, *, web_search: bool = False
    ) -> AsyncIterator[str]:
        """Streaming: yields response text chunks as they arrive from the
        model/web_search node, via LangGraph's custom stream mode (see
        get_stream_writer usage in those nodes).

        web_search=True forces this turn straight to the web_search route,
        bypassing the router's classification call entirely (see
        router_node.py) - it's how the frontend's explicit web-search toggle
        reaches the graph. False (default) leaves routing to the classifier,
        which only ever chooses "normal" or "rag" on its own.

        See get_route()/get_retrieved_sources()/get_web_search_sources() to
        inspect what actually happened after the fact."""
        async for chunk in self._graph.astream(
            self._initial_state(user_input, web_search=web_search),
            config=self._config(chat_id),
            stream_mode="custom",
        ):
            yield chunk

    async def _state_value(self, chat_id: uuid.UUID, key: str):
        snapshot = await self._graph.aget_state(self._config(chat_id))
        if snapshot is None or snapshot.values is None:
            return None
        return snapshot.values.get(key)

    async def get_route(self, chat_id: uuid.UUID) -> Route | None:
        """Reads back which route the router chose for the most recent
        turn - observability/debugging (Phase 14 doc section 19), not used
        for any behavioral decision."""
        return await self._state_value(chat_id, "route")

    async def get_retrieved_sources(self, chat_id: uuid.UUID) -> list[RetrievedChunk]:
        """Reads back the retrieved_context the most recent graph run wrote
        to this thread's checkpointed state. Called after run_stream()
        completes, to attach source attribution to the assistant message
        that's about to be cached/persisted (see messages.py) - kept
        separate from run_stream() itself so streaming's yield type stays
        plain text chunks, not a tagged union of text and metadata. Empty
        on any turn that didn't route to RAG."""
        return await self._state_value(chat_id, "retrieved_context") or []

    async def get_web_search_sources(self, chat_id: uuid.UUID) -> list[WebSearchSource]:
        """Web-search counterpart to get_retrieved_sources - empty on any
        turn that didn't route to web_search, or that did but Tavily
        returned no results (see web_search_node.py)."""
        return await self._state_value(chat_id, "web_search_sources") or []

    async def get_tool_calls_made(self, chat_id: uuid.UUID) -> list[str]:
        """Which MCP tool(s) (if any) agent_node actually invoked this turn -
        empty on any turn that didn't route to "normal", or that did but the
        model answered without needing a tool. Observability only, for the
        frontend's subtle tool-use indicator (Phase 17 doc section 20) - see
        messages.py."""
        return await self._state_value(chat_id, "tool_calls_made") or []
