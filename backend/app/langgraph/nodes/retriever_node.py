"""Retriever node - the new first node in the graph (Phase 12).

Reads the latest user message from state["messages"] as the query, searches
the vector store via Retriever, and writes the results to
state["retrieved_context"] for the model node to consume. Runs before the
model node so the model always sees this turn's retrieval alongside
conversation history - see app/langgraph/graphs/chat_graph.py.
"""
import logging
from collections.abc import Awaitable, Callable

from langchain_core.messages import AnyMessage, HumanMessage

from app.langgraph.state import ChatState
from app.rag.retriever import Retriever

logger = logging.getLogger(__name__)


def make_retriever_node(retriever: Retriever) -> Callable[[ChatState], Awaitable[ChatState]]:
    async def retriever_node(state: ChatState) -> ChatState:
        query = _latest_user_query(state["messages"])
        if query is None:
            return {"retrieved_context": []}

        chunks = await retriever.retrieve(query)
        logger.debug("retriever_node found %d chunk(s) for query %r", len(chunks), query)
        return {"retrieved_context": chunks}

    return retriever_node


def _latest_user_query(messages: list[AnyMessage]) -> str | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content if isinstance(message.content, str) else str(message.content)
    return None
