"""The chat graph.

Current flow:

    messages -> [model] -> END

Every chat message must be run through chat_graph — no code path is allowed
to call Gemini directly (app/services/chat_execution_service.py is the only
intended entry point). Future nodes (memory, RAG, tool calling, SQL agent,
web search, reflection, planner, multi-agent) are added by inserting them
between the entry point and "model", or branching after it; the
build/compile pattern below does not need to change to support that.

build_chat_graph takes a ModelService rather than constructing one itself, so
this module has no idea whether it's been handed Gemini or something else -
see app/services/model_service.py.

Compiling with a checkpointer is what turns chat_id into a LangGraph
thread_id: the checkpointer persists ChatState per thread_id, so the caller
(ChatExecutionService) only ever needs to pass in the new turn's message, not
the whole conversation.
"""
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.langgraph.nodes.model_node import make_model_node
from app.langgraph.state import ChatState
from app.services.model_service import ModelService

MODEL_NODE = "model"


def build_chat_graph(
    model_service: ModelService,
    *,
    checkpointer: BaseCheckpointSaver,
    max_history_messages: int,
) -> CompiledStateGraph:
    workflow = StateGraph(ChatState)

    workflow.add_node(
        MODEL_NODE, make_model_node(model_service, max_history_messages=max_history_messages)
    )

    workflow.set_entry_point(MODEL_NODE)
    workflow.add_edge(MODEL_NODE, END)

    return workflow.compile(checkpointer=checkpointer)
