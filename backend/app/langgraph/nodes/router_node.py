"""Router node - the entry point of the chat graph.

Classifies the user's latest message into "normal" or "rag" using Gemini's
structured output (constrained to those two literal values), not keyword
matching - a keyword check can't distinguish intent from topic (e.g. "what
does the document say about X" vs. a general knowledge question that happens
to mention the same subject).

This is a genuinely separate Gemini call from the one that generates the
final answer (see model_node.py) - kept deliberately small (short system
instructions, a trimmed slice of history, a single-token-ish JSON reply) so
the "don't waste API calls" concern the Phase 14 doc raises is a real,
minimal cost, not a second full generation.

Also resets retrieved_context to its empty default on EVERY turn, regardless
of the chosen route - see app/langgraph/state.py's docstring for why this
matters (without it, a route switch mid-conversation would leak the previous
turn's stale retrieval into a route that never touched it this turn).

Phase 14.6: "web_search" is deliberately NOT one of the classifier's choices.
It's never inferred from the message text - it's an explicit, caller-supplied
override (state["web_search_requested"], set from the frontend's web-search
toggle - see chat_execution_service.py). When set, this node skips the
classification call entirely and routes straight to "web_search": the user
has already told us unambiguously what they want, so spending an API call to
guess would be pure waste, and there's no ambiguity for a classifier to
usefully resolve.
"""
import logging
from collections.abc import Awaitable, Callable

from langchain_core.messages import AnyMessage, HumanMessage

from app.langgraph.state import ChatState, Route
from app.services.model_service import ModelService, ModelTurn

logger = logging.getLogger(__name__)

_ROUTES: list[str] = ["normal", "rag"]

_ROUTER_INSTRUCTIONS = """You are a routing classifier for an AI chatbot. Given the conversation so \
far, decide which ONE capability should handle the user's LATEST message. Respond with exactly one \
of: "normal", "rag".

- "rag": the user is asking about a specific document that was uploaded/indexed into this chatbot's \
knowledge base (e.g. "what does the document say about X", "according to the handbook...", "explain \
section 3", "what does the uploaded PDF say about..."). Only choose this when the question is clearly \
about THAT indexed document, not general knowledge.

- "normal": everything else - general knowledge questions, coding help, casual conversation, or a \
question that references something ambiguous with no antecedent anywhere in this conversation - in \
that case a normal conversational reply (which can ask the user to clarify) is safer than guessing.

Use the conversation history to resolve references like "it", "their", "that" - e.g. if an earlier turn \
established a document topic, a follow-up like "why is that important?" should route the same way the \
earlier turn would have, using that established context, not be treated as having no context.

When genuinely uncertain and nothing in the conversation resolves the ambiguity, prefer "normal" over \
guessing "rag" - a normal reply can ask a clarifying question; a wrong retrieval call cannot."""


def _to_turn(message: AnyMessage) -> ModelTurn:
    role = "user" if isinstance(message, HumanMessage) else "model"
    content = message.content if isinstance(message.content, str) else str(message.content)
    return {"role": role, "content": content}


def make_router_node(
    model_service: ModelService, *, context_messages: int
) -> Callable[[ChatState], Awaitable[ChatState]]:
    async def router_node(state: ChatState) -> ChatState:
        if state.get("web_search_requested"):
            logger.info("route=web_search (explicit override, no classification call)")
            return {"route": "web_search", "retrieved_context": []}

        trimmed = state["messages"][-context_messages:]
        history = [_to_turn(message) for message in trimmed]

        try:
            choice = await model_service.classify(
                history, instructions=_ROUTER_INSTRUCTIONS, choices=_ROUTES
            )
            route: Route = choice  # type: ignore[assignment]  # classify() guarantees choice in _ROUTES
        except Exception:
            # A router failure must never take the whole turn down, and
            # must never silently default to a retrieval route it can't
            # justify - "normal" is the one route that's always safe: the
            # model can still answer from conversation context, or ask the
            # user to clarify, without calling anything external.
            logger.exception("Router classification failed - falling back to 'normal'")
            route = "normal"

        logger.info("route=%s", route)
        return {"route": route, "retrieved_context": []}

    return router_node
