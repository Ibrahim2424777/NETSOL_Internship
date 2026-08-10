"""Model node — the single node in the current graph.

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
"""
import logging
from collections.abc import Awaitable, Callable

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.config import get_stream_writer

from app.langgraph.state import ChatState
from app.services.model_service import ModelService, ModelTurn

logger = logging.getLogger(__name__)


def _to_turn(message: AnyMessage) -> ModelTurn:
    role = "user" if isinstance(message, HumanMessage) else "model"
    content = message.content if isinstance(message.content, str) else str(message.content)
    return {"role": role, "content": content}


def make_model_node(
    model_service: ModelService, *, max_history_messages: int
) -> Callable[[ChatState], Awaitable[ChatState]]:
    async def model_node(state: ChatState) -> ChatState:
        trimmed = state["messages"][-max_history_messages:]
        history = [_to_turn(message) for message in trimmed]
        logger.debug("model_node calling model service with %d turns of history", len(history))

        writer = get_stream_writer()
        chunks: list[str] = []
        async for chunk in model_service.generate_stream(history):
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
