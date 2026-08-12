"""Web search node (Phase 14.6) - the terminal node on the "web_search"
branch of the chat graph.

Unlike the RAG/model split (retrieve structured data, then hand it to a
separate model node to write the answer), this node's model call - Groq's
groq/compound-mini - does its own web search AND writes the final answer in
one step, so there's no separate retrieval-then-generation here. That's why
this branch does NOT converge on the shared model node the way "rag" and
"normal" do (see chat_graph.py): there's nothing left for that node to do.

The ModelService this node is built with (see app/api/deps.py) is expected
to be compound-mini wrapped as PRIMARY with Gemini as FALLBACK - the reverse
of the app's default Gemini-primary/Groq-fallback pairing used everywhere
else, because for this one route the search capability itself is the reason
to call Groq at all. Gemini has no equivalent built-in search in this
integration, so a Gemini fallback here means "answer from its own general
knowledge, without live search" rather than "search a different way" - still
strictly better than the turn failing outright.
"""
import logging
from collections.abc import Awaitable, Callable

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.config import get_stream_writer

from app.langgraph.state import ChatState, WebSearchSource
from app.services.model_service import ModelService, ModelTurn, SearchCitation

logger = logging.getLogger(__name__)

_WEB_SEARCH_INSTRUCTIONS = (
    "Instructions: Answer with the most current, accurate information you "
    "can. This question involves time-sensitive details (dates, scores, "
    "prices, schedules, current events, recent news) - if you are not "
    "confident your knowledge is current, say so clearly instead of "
    "guessing."
)


def _to_turn(message: AnyMessage) -> ModelTurn:
    role = "user" if isinstance(message, HumanMessage) else "model"
    content = message.content if isinstance(message.content, str) else str(message.content)
    return {"role": role, "content": content}


def _build_search_turns(history: list[ModelTurn]) -> list[ModelTurn]:
    if not history or history[-1]["role"] != "user":
        return history
    augmented = f"{history[-1]['content']}\n\n{_WEB_SEARCH_INSTRUCTIONS}"
    return [*history[:-1], {"role": "user", "content": augmented}]


def make_web_search_node(
    model_service: ModelService, *, max_history_messages: int
) -> Callable[[ChatState], Awaitable[ChatState]]:
    async def web_search_node(state: ChatState) -> ChatState:
        trimmed = state["messages"][-max_history_messages:]
        history = _build_search_turns([_to_turn(message) for message in trimmed])

        # Ordered de-dup by URL: compound-mini can (and often does) run
        # several searches for one answer, sometimes surfacing the same
        # page more than once across them - the UI wants one chip per
        # distinct source, not one per search call.
        seen_urls: set[str] = set()
        sources: list[WebSearchSource] = []

        def on_search_result(citation: SearchCitation) -> None:
            if citation["url"] in seen_urls:
                return
            seen_urls.add(citation["url"])
            sources.append({"title": citation["title"], "url": citation["url"]})

        writer = get_stream_writer()
        chunks: list[str] = []
        async for chunk in model_service.generate_stream(history, on_search_result=on_search_result):
            chunks.append(chunk)
            writer(chunk)

        full_response = "".join(chunks)
        if not full_response:
            raise RuntimeError("Model service returned an empty response")

        logger.debug("web_search_node found %d source(s)", len(sources))
        return {"messages": [AIMessage(content=full_response)], "web_search_sources": sources}

    return web_search_node
