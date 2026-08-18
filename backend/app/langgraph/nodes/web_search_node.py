"""Web search retrieval node (Phase 18, rewritten from Phase 14.6's
compound-mini implementation) - the first node on the "web_search" branch of
the chat graph, converging on web_search_answer_node.py for generation (see
chat_graph.py).

Previously this node's model call (Groq's compound-mini) did its own
autonomous web search AND wrote the final answer in one step. That's been
replaced: compound-mini could (and reproducibly did, live) attempt to
retrieve too many/too-large pages and fail the whole turn with a 413 on
ordinary queries - not fixable from this app's side (see groq_service.py's
git history for what was tried). Tavily now owns retrieval exclusively, and
this node's only job is turning the user's question into a bounded set of
search results - the same retrieve-then-generate split RAG already uses
(retriever_node.py + model_node.py), kept as its own separate system rather
than merged with RAG (different content, different citation shape,
different failure modes - see app/langgraph/state.py).
"""
import logging
from collections.abc import Awaitable, Callable

from langchain_core.messages import AnyMessage, HumanMessage

from app.langgraph.state import ChatState
from app.services.tavily_service import TavilyError, TavilySearchService

logger = logging.getLogger(__name__)


def _latest_user_query(messages: list[AnyMessage]) -> str | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content if isinstance(message.content, str) else str(message.content)
    return None


def make_web_search_node(
    tavily_service: TavilySearchService,
) -> Callable[[ChatState], Awaitable[ChatState]]:
    async def web_search_node(state: ChatState) -> ChatState:
        query = _latest_user_query(state["messages"])
        if query is None:
            return {"web_search_results": [], "web_search_sources": []}

        try:
            results = await tavily_service.search(query)
        except TavilyError as exc:
            # Graceful degradation (Phase 18 doc section 15) - the answer
            # node still runs; it just has nothing to ground a reply in,
            # and its own instructions tell the model to say so rather than
            # guess (see web_search_answer_node.py's _NO_RESULTS_INSTRUCTIONS).
            # Same "degrade, don't crash the turn" precedent as MCP's
            # list_tools() failure in agent_node.py.
            logger.warning("Tavily search failed for web_search route: %s", exc)
            results = []

        logger.debug("web_search_node found %d result(s) for query %r", len(results), query)
        sources = [{"title": result["title"], "url": result["url"]} for result in results]
        return {"web_search_results": results, "web_search_sources": sources}

    return web_search_node
