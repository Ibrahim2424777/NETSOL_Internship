"""Model node — the second node in the graph, after the retriever (Phase 12).

make_model_node is a factory, not the node itself: it takes a ModelService
and returns a node function closed over it. This is how the injected
dependency reaches a plain LangGraph node function (which LangGraph calls as
node(state), with no constructor to inject into) - the node body never
imports or knows about Gemini specifically, only the ModelService interface.

Streams internally via get_stream_writer() so a caller using
graph.astream(..., stream_mode="custom") sees each chunk as it arrives from
Gemini. get_stream_writer() is a documented no-op outside a "custom" stream
context, so a plain graph.ainvoke() still works unchanged and just gets the
fully-accumulated response once the node returns.

state["messages"] is the full thread history as loaded by the checkpointer
(see app/langgraph/state.py) - it's trimmed to the most recent
max_history_messages turns here, right before the model call, rather than
upstream, so "how much context Gemini gets" stays a single, visible decision
in the one place that actually talks to the model.

state["retrieved_context"] (Phase 12) is folded into the CURRENT turn only -
see _build_grounded_turns. Older turns in history are left as plain text:
they were already answered (grounded on their own retrieval at the time),
and re-injecting retrieval boilerplate into every historical turn on every
call would both bloat the prompt and duplicate context Gemini already
responded to once. Only state["messages"] itself (not this augmented copy)
is what gets checkpointed, so the retrieval framing never leaks into
persisted conversation history.
"""
import logging
from collections.abc import Awaitable, Callable

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.config import get_stream_writer

from app.langgraph.state import ChatState
from app.services.model_service import ModelService, ModelTurn
from app.services.vector_store_service import RetrievedChunk

logger = logging.getLogger(__name__)

_GROUNDING_INSTRUCTIONS = (
    "Instructions: Prefer the retrieved context above when answering. Answer "
    "using the retrieved information where it is relevant. Do not invent "
    "facts that are not supported by the retrieved context or the "
    "conversation. If the retrieved context does not contain enough "
    "information to answer, clearly say so. Never claim information came "
    "from the document if it did not."
)


def _to_turn(message: AnyMessage) -> ModelTurn:
    role = "user" if isinstance(message, HumanMessage) else "model"
    content = message.content if isinstance(message.content, str) else str(message.content)
    return {"role": role, "content": content}


def _format_chunk(chunk: RetrievedChunk) -> str:
    location = f", Page: {chunk['page']}" if chunk["page"] is not None else ""
    return f"[Source: {chunk['source']}{location}]\n{chunk['content']}"


def _build_grounded_turns(
    history: list[ModelTurn], retrieved: list[RetrievedChunk]
) -> list[ModelTurn]:
    """Rewrites only the last (current) turn's content to include retrieved
    context, leaving every earlier turn untouched. No-ops if there's nothing
    retrieved - e.g. before any document has been ingested, or when the
    query has no relevant match - so a plain conversational answer is still
    possible without a dangling empty "Retrieved Context:" block."""
    if not retrieved or not history or history[-1]["role"] != "user":
        return history

    context_block = "\n\n".join(_format_chunk(chunk) for chunk in retrieved)
    grounded_content = (
        f"Retrieved Context:\n\n{context_block}\n\n"
        f"User Question:\n{history[-1]['content']}\n\n"
        f"{_GROUNDING_INSTRUCTIONS}"
    )
    return [*history[:-1], {"role": "user", "content": grounded_content}]


def make_model_node(
    model_service: ModelService, *, max_history_messages: int
) -> Callable[[ChatState], Awaitable[ChatState]]:
    async def model_node(state: ChatState) -> ChatState:
        trimmed = state["messages"][-max_history_messages:]
        history = [_to_turn(message) for message in trimmed]
        retrieved = state.get("retrieved_context") or []
        grounded_history = _build_grounded_turns(history, retrieved)
        logger.debug(
            "model_node calling model service with %d turns of history, %d retrieved chunk(s)",
            len(grounded_history),
            len(retrieved),
        )

        writer = get_stream_writer()
        chunks: list[str] = []
        async for chunk in model_service.generate_stream(grounded_history):
            chunks.append(chunk)
            writer(chunk)

        full_response = "".join(chunks)
        if not full_response:
            # Raise rather than returning an empty AIMessage: a node that
            # returns normally has its state update checkpointed, and an
            # empty model turn would (a) desync the checkpoint from Postgres,
            # which never persists a failed turn, and (b) get resent to
            # Gemini as context on the next turn. The endpoint's existing
            # try/except around run_stream already turns this into the same
            # generic "assistant failed to respond" SSE error as any other
            # model-layer exception.
            raise RuntimeError("Model service returned an empty response")

        return {"messages": [AIMessage(content=full_response)]}

    return model_node
