"""The chat graph (Phase 14, routing restructured in Phase 14.6).

Current flow:

               ┌─ rag ────→ [retriever] ─┐
    [router] ──┼─ normal ────────────────┼──→ [model] → END
               └─ web_search ────────────→ [web_search] → END

Every chat message must be run through chat_graph — no code path is allowed
to call Gemini/Groq directly (app/services/chat_execution_service.py is the
only intended entry point). The router decides, per turn, which node runs
next - see router_node.py for how, and app/langgraph/state.py for why
retrieved_context gets reset on every turn regardless of which branch is
taken.

"web_search" is the odd one out: it does NOT converge on the shared model
node the way "rag" and "normal" do. RAG/normal both follow a
retrieve-then-generate split where a separate node (model) writes the
answer; web_search's model call (Groq's compound-mini) does its own search
AND writes the final answer in a single step, so there's nothing left for
the model node to do on that branch - see web_search_node.py.

build_chat_graph takes a ModelService for routing/normal/RAG, a SEPARATE
ModelService for web search, and a RAG Retriever rather than constructing
them itself, so this module has no idea whether it's been handed Gemini vs.
something else, LanceDB vs. something else, or which two providers the web
search service is composed of - see app/services/model_service.py and
app/rag/retriever.py. Two different ModelService instances (not one) because
the "right" primary/fallback pairing is reversed between them: routing/
normal/RAG want Gemini primary with Groq as fallback, while web_search wants
Groq's compound-mini primary (the whole reason to route here is its search
capability) with Gemini as fallback - see app/api/deps.py.

Compiling with a checkpointer is what turns chat_id into a LangGraph
thread_id: the checkpointer persists ChatState per thread_id, so the caller
(ChatExecutionService) only ever needs to pass in the new turn's message, not
the whole conversation.
"""
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.langgraph.nodes.model_node import make_model_node
from app.langgraph.nodes.retriever_node import make_retriever_node
from app.langgraph.nodes.router_node import make_router_node
from app.langgraph.nodes.web_search_node import make_web_search_node
from app.langgraph.state import ChatState, Route
from app.rag.retriever import Retriever
from app.services.model_service import ModelService

ROUTER_NODE = "router"
RETRIEVER_NODE = "retriever"
WEB_SEARCH_NODE = "web_search"
MODEL_NODE = "model"


def _select_route(state: ChatState) -> str:
    """The conditional-edge function LangGraph calls right after the router
    node - reads the decision it wrote to state and returns which node
    should run next. Defensive fallback to MODEL_NODE (the "normal" path)
    if `route` is ever missing, matching router_node's own safe-default
    behavior on classification failure."""
    route: Route | None = state.get("route")
    if route == "rag":
        return RETRIEVER_NODE
    if route == "web_search":
        return WEB_SEARCH_NODE
    return MODEL_NODE


def build_chat_graph(
    model_service: ModelService,
    web_search_model_service: ModelService,
    retriever: Retriever,
    *,
    checkpointer: BaseCheckpointSaver,
    max_history_messages: int,
    router_context_messages: int,
) -> CompiledStateGraph:
    workflow = StateGraph(ChatState)

    workflow.add_node(
        ROUTER_NODE, make_router_node(model_service, context_messages=router_context_messages)
    )
    workflow.add_node(RETRIEVER_NODE, make_retriever_node(retriever))
    workflow.add_node(
        WEB_SEARCH_NODE,
        make_web_search_node(web_search_model_service, max_history_messages=max_history_messages),
    )
    workflow.add_node(
        MODEL_NODE, make_model_node(model_service, max_history_messages=max_history_messages)
    )

    workflow.set_entry_point(ROUTER_NODE)
    workflow.add_conditional_edges(
        ROUTER_NODE,
        _select_route,
        {RETRIEVER_NODE: RETRIEVER_NODE, WEB_SEARCH_NODE: WEB_SEARCH_NODE, MODEL_NODE: MODEL_NODE},
    )
    workflow.add_edge(RETRIEVER_NODE, MODEL_NODE)
    workflow.add_edge(WEB_SEARCH_NODE, END)
    workflow.add_edge(MODEL_NODE, END)

    return workflow.compile(checkpointer=checkpointer)
