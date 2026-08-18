"""The chat graph (Phase 14, restructured 14.6, MCP tool-calling added Phase 17).

Current flow:

               ┌─ rag ────→ [retriever] ──────→ [model] ──┐
    [router] ──┼─ web_search ────────────→ [web_search] ──┼──→ END
               └─ normal ─────────────────→ [agent] ──────┘

Every chat message must be run through chat_graph — no code path is allowed
to call Gemini/Groq (or, as of Phase 17, the MCP server) directly -
app/services/chat_execution_service.py is the only intended entry point. The
router decides, per turn, which node runs next - see router_node.py for how,
and app/langgraph/state.py for why retrieved_context/tool_calls_made get
reset on every turn regardless of which branch is taken.

Three of the four non-router nodes are unchanged since Phase 14.6 - only
"normal" changed destination. It used to share MODEL_NODE with "rag"; now it
goes to AGENT_NODE instead (see agent_node.py), which can call MCP tools
(weather, email) the plain model node never could. RAG keeps using the
plain, non-tool-calling model node deliberately - grounding an answer in
retrieved document content and offering it live external tools are
different concerns, and mixing them would make RAG answers less
predictable for no clear benefit (see agent_node.py's own docstring).
web_search still doesn't converge on model_node either, for the reason
established in Phase 14.6: Groq's compound-mini writes the final answer
itself in one step.

build_chat_graph takes a ModelService for routing/normal/RAG, a SEPARATE
ModelService for web search, an MCPClientService for tool discovery/
execution, and a RAG Retriever, rather than constructing any of them itself -
this module has no idea whether it's been handed Gemini vs. something else,
LanceDB vs. something else, which two providers the web search service is
composed of, or where the MCP server lives. See app/services/model_service.py,
app/mcp/client.py, app/rag/retriever.py, and app/api/deps.py.

Compiling with a checkpointer is what turns chat_id into a LangGraph
thread_id: the checkpointer persists ChatState per thread_id, so the caller
(ChatExecutionService) only ever needs to pass in the new turn's message, not
the whole conversation.
"""
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.langgraph.nodes.agent_node import make_agent_node
from app.langgraph.nodes.model_node import make_model_node
from app.langgraph.nodes.retriever_node import make_retriever_node
from app.langgraph.nodes.router_node import make_router_node
from app.langgraph.nodes.web_search_node import make_web_search_node
from app.langgraph.state import ChatState, Route
from app.mcp.client import MCPClientService
from app.rag.retriever import Retriever
from app.services.model_service import ModelService

ROUTER_NODE = "router"
RETRIEVER_NODE = "retriever"
WEB_SEARCH_NODE = "web_search"
AGENT_NODE = "agent"
MODEL_NODE = "model"


def _select_route(state: ChatState) -> str:
    """The conditional-edge function LangGraph calls right after the router
    node - reads the decision it wrote to state and returns which node
    should run next. Defensive fallback to AGENT_NODE (the "normal" path)
    if `route` is ever missing, matching router_node's own safe-default
    behavior on classification failure."""
    route: Route | None = state.get("route")
    if route == "rag":
        return RETRIEVER_NODE
    if route == "web_search":
        return WEB_SEARCH_NODE
    return AGENT_NODE


def build_chat_graph(
    model_service: ModelService,
    web_search_model_service: ModelService,
    retriever: Retriever,
    mcp_client: MCPClientService,
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
        AGENT_NODE,
        make_agent_node(model_service, mcp_client, max_history_messages=max_history_messages),
    )
    workflow.add_node(
        MODEL_NODE, make_model_node(model_service, max_history_messages=max_history_messages)
    )

    workflow.set_entry_point(ROUTER_NODE)
    workflow.add_conditional_edges(
        ROUTER_NODE,
        _select_route,
        {RETRIEVER_NODE: RETRIEVER_NODE, WEB_SEARCH_NODE: WEB_SEARCH_NODE, AGENT_NODE: AGENT_NODE},
    )
    workflow.add_edge(RETRIEVER_NODE, MODEL_NODE)
    workflow.add_edge(WEB_SEARCH_NODE, END)
    workflow.add_edge(AGENT_NODE, END)
    workflow.add_edge(MODEL_NODE, END)

    return workflow.compile(checkpointer=checkpointer)
