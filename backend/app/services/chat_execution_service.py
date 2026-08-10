"""Runs the chat graph end-to-end for a single turn.

This is the intended entry point for the rest of the app to get an AI
response - the Messages endpoint calls run_stream(...) rather than touching
the graph or Gemini directly, so "every request passes through LangGraph"
holds by construction, not just by convention.

chat_id doubles as the LangGraph thread_id: each call passes only the new
turn's HumanMessage as input, and the checkpointer supplies everything the
model has said/heard before in that chat. Isolation between chats/users falls
out of thread_id scoping in the checkpointer itself - callers must still only
ever pass a chat_id the caller has already verified the current user owns
(see OwnedChat in app/api/deps.py); this service does not re-check ownership.
"""
import uuid
from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from app.langgraph.graphs.chat_graph import build_chat_graph
from app.langgraph.state import ChatState
from app.services.model_service import ModelService


class ChatExecutionService:
    def __init__(
        self,
        model_service: ModelService,
        *,
        checkpointer: BaseCheckpointSaver,
        max_history_messages: int,
    ) -> None:
        self._checkpointer = checkpointer
        self._graph: CompiledStateGraph = build_chat_graph(
            model_service, checkpointer=checkpointer, max_history_messages=max_history_messages
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

    async def run(self, chat_id: uuid.UUID, user_input: str) -> str:
        """Non-streaming: run the graph to completion and return the full
        response. Not used by the chat-message endpoint (which streams), but
        kept for callers that just want a single result - e.g. a future
        auto-title-generation feature."""
        initial_state: ChatState = {"messages": [HumanMessage(content=user_input)]}
        result = await self._graph.ainvoke(initial_state, config=self._config(chat_id))

        messages = result["messages"]
        if not messages:
            raise RuntimeError("Chat graph completed without producing a response")
        return messages[-1].content

    async def run_stream(self, chat_id: uuid.UUID, user_input: str) -> AsyncIterator[str]:
        """Streaming: yields response text chunks as they arrive from the
        model node, via LangGraph's custom stream mode (see
        app/langgraph/nodes/model_node.py's use of get_stream_writer)."""
        initial_state: ChatState = {"messages": [HumanMessage(content=user_input)]}
        async for chunk in self._graph.astream(
            initial_state, config=self._config(chat_id), stream_mode="custom"
        ):
            yield chunk
