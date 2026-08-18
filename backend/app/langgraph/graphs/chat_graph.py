"""The chat graph (Phase 14, restructured 14.6, MCP tool-calling added Phase
17, web search moved to Tavily Phase 18).

Current flow:

               ┌─ rag ────→ [retriever] ───────────→ [model] ────────┐
    [router] ──┼─ web_search ──→ [web_search] ──→ [web_search_answer] ┼──→ END
               └─ normal ─────────────────────────→ [agent] ─────────┘

Every chat message must be run through chat_graph — no code path is allowed
to call Gemini/Groq (or, as of Phase 17, the MCP server; or, as of Phase 18,
Tavily) directly - app/services/chat_execution_service.py is the only
intended entry point. The router decides, per turn, which node runs next -
see router_node.py for how, and app/langgraph/state.py for why
retrieved_context/tool_calls_made get reset on every turn regardless of
which branch is taken.

"normal" goes to AGENT_NODE (see agent_node.py), which can call MCP tools
(weather, email) the plain model node never could. RAG keeps using the
plain, non-tool-calling model node deliberately - grounding an answer in
retrieved document content and offering it live external tools are
different concerns, and mixing them would make RAG answers less predictable
for no clear benefit (see agent_node.py's own docstring).

web_search now DOES converge on a shared-shape generation step, same as RAG
- but its own dedicated one (WEB_SEARCH_ANSWER_NODE), not model_node.py
itself, since RAG and web search are different systems (see
app/langgraph/state.py). Before Phase 18, web_search didn't converge on
anything: Groq's compound-mini wrote the final answer itself in one step.
That's gone - Tavily (WEB_SEARCH_NODE) retrieves, then WEB_SEARCH_ANSWER_NODE
generates through the same Gemini-primary/Groq-fallback ModelService every
other route uses.

build_chat_graph takes a ModelService for routing/normal/RAG/web-search-
generation, a TavilySearchService for web search retrieval, an
MCPClientService for tool discovery/execution, and a RAG Retriever, rather
than constructing any of them itself - this module has no idea whether it's
been handed Gemini vs. something else, LanceDB vs. something else, or where
the MCP/Tavily services actually live. See app/services/model_service.py,
app/services/tavily_service.py, app/mcp/client.py, app/rag/retriever.py, and
app/api/deps.py.

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
from app.langgraph.nodes.web_search_answer_node import make_web_search_answer_node
from app.langgraph.nodes.web_search_node import make_web_search_node
from app.langgraph.state import ChatState, Route
from app.mcp.client import MCPClientService
from app.rag.retriever import Retriever
from app.services.model_service import ModelService
from app.services.tavily_service import TavilySearchService

ROUTER_NODE = "router"
RETRIEVER_NODE = "retriever"
WEB_SEARCH_NODE = "web_search"
WEB_SEARCH_ANSWER_NODE = "web_search_answer"
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
    tavily_service: TavilySearchService,
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
    workflow.add_node(WEB_SEARCH_NODE, make_web_search_node(tavily_service))
    workflow.add_node(
        WEB_SEARCH_ANSWER_NODE,
        make_web_search_answer_node(model_service, max_history_messages=max_history_messages),
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
    workflow.add_edge(WEB_SEARCH_NODE, WEB_SEARCH_ANSWER_NODE)
    workflow.add_edge(WEB_SEARCH_ANSWER_NODE, END)
    workflow.add_edge(AGENT_NODE, END)
    workflow.add_edge(MODEL_NODE, END)

    return workflow.compile(checkpointer=checkpointer)
