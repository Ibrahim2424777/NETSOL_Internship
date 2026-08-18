"""Web search answer node (Phase 18) - the second node on the "web_search"
branch, generating a grounded reply from web_search_node.py's Tavily results
(see chat_graph.py).

Mirrors model_node.py's retrieve-then-generate shape for RAG, but kept as
its own file/system rather than merged with it (Phase 18 doc section 12:
RAG is the app's private/document knowledge, web search is the public web
via Tavily - different content, different citation shape, and mixing them
would make either harder to reason about for no benefit - see
app/langgraph/state.py).

Uses the SAME ModelService as normal/RAG (Gemini primary, Groq fallback -
see app/api/deps.py's get_model_service). Phase 14.6's separate
compound-mini-primary pairing is gone along with compound-mini itself:
Tavily already did the retrieval, so there's no reason for this route to
talk to a different provider than everything else.
"""
import logging
from collections.abc import Awaitable, Callable

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.config import get_stream_writer

from app.langgraph.state import ChatState
from app.services.model_service import ModelService, ModelTurn
from app.services.tavily_service import TavilySearchResult

logger = logging.getLogger(__name__)

_GROUNDING_INSTRUCTIONS = (
    "Instructions: Answer using the web search results above where relevant - "
    "they reflect current, live information as of right now. Prefer them over "
    "your own training data for anything time-sensitive (dates, scores, "
    "prices, schedules, current events, recent news). Do not invent facts "
    "that aren't present above or in the conversation. If the results don't "
    "contain enough information to answer, say so clearly instead of guessing."
)

# Used instead of _GROUNDING_INSTRUCTIONS when Tavily returned nothing this
# turn (a genuinely empty result set, or a search failure web_search_node.py
# already degraded gracefully from) - the model still answers, but is told
# explicitly that it has no live data, satisfying the doc's "do not silently
# fabricate an answer" requirement (section 15) in both cases identically.
_NO_RESULTS_INSTRUCTIONS = (
    "Instructions: Web search did not return any results for this turn (it "
    "may be temporarily unavailable, or the query returned nothing useful). "
    "Answer from your own knowledge, but if the question needs current, "
    "time-sensitive information (recent events, scores, prices, schedules) "
    "that you can't be confident is still accurate, say so clearly instead "
    "of guessing."
)


def _to_turn(message: AnyMessage) -> ModelTurn:
    role = "user" if isinstance(message, HumanMessage) else "model"
    content = message.content if isinstance(message.content, str) else str(message.content)
    return {"role": role, "content": content}


def _format_result(result: TavilySearchResult) -> str:
    return f"[Source: {result['title']} ({result['url']})]\n{result['content']}"


def _build_grounded_turns(history: list[ModelTurn], results: list[TavilySearchResult]) -> list[ModelTurn]:
    """Rewrites only the last (current) turn's content to include Tavily's
    results, leaving every earlier turn untouched - same shape as
    model_node.py's RAG equivalent, kept separate per this module's own
    docstring. Still adds an instruction when results are empty (unlike
    RAG's no-op-on-empty behavior) so a Tavily failure never reads to the
    model as "no need to mention search wasn't used" - see
    _NO_RESULTS_INSTRUCTIONS."""
    if not history or history[-1]["role"] != "user":
        return history

    if results:
        context_section = "Web Search Results:\n\n" + "\n\n".join(_format_result(r) for r in results)
        grounded_content = (
            f"{context_section}\n\n"
            f"User Question:\n{history[-1]['content']}\n\n"
            f"{_GROUNDING_INSTRUCTIONS}"
        )
    else:
        grounded_content = f"{history[-1]['content']}\n\n{_NO_RESULTS_INSTRUCTIONS}"

    return [*history[:-1], {"role": "user", "content": grounded_content}]


def make_web_search_answer_node(
    model_service: ModelService, *, max_history_messages: int
) -> Callable[[ChatState], Awaitable[ChatState]]:
    async def web_search_answer_node(state: ChatState) -> ChatState:
        trimmed = state["messages"][-max_history_messages:]
        history = [_to_turn(message) for message in trimmed]
        results = state.get("web_search_results") or []
        grounded_history = _build_grounded_turns(history, results)
        logger.debug(
            "web_search_answer_node calling model service with %d turns of history, %d search result(s)",
            len(grounded_history),
            len(results),
        )

        writer = get_stream_writer()
        chunks: list[str] = []
        async for chunk in model_service.generate_stream(grounded_history):
            chunks.append(chunk)
            writer(chunk)

        full_response = "".join(chunks)
        if not full_response:
            raise RuntimeError("Model service returned an empty response")

        return {"messages": [AIMessage(content=full_response)]}

    return web_search_answer_node
