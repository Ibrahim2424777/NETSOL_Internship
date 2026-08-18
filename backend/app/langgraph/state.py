"""Shared state passed between LangGraph nodes.

Every node reads from and writes to this single structure as it flows through
the graph. `messages` is the full conversation for the current thread
(chat_id) as loaded from the checkpointer, plus whatever a node appends -
`add_messages` is a reducer, not a plain field assignment: a node returning
{"messages": [new_message]} appends, it never overwrites what the checkpointer
already loaded. This is what lets callers pass only the new turn's message as
input instead of replaying the whole history on every call.

`retrieved_context` (Phase 12) and `web_search_sources` (Phase 14.6) are plain
fields with no reducer - each run of their respective node OVERWRITES them
with this turn's results, unlike `messages`. That's deliberate: retrieval is
per-question, not cumulative conversation history. They still get
checkpointed as part of the overall state (LangGraph checkpoints the whole
dict), but the node that owns each field always overwrites it before it's
read downstream, so a stale value from a previous turn is never actually
seen.

`route` (Phase 14) is the router node's decision for the CURRENT turn only
("normal" | "rag" | "web_search") - it exists purely so the conditional edge
leaving the router node (see app/langgraph/graphs/chat_graph.py) has
something in state to read, since LangGraph's conditional-edge functions
choose the next node based on state, not a node's return value directly.
It's not meant to be read by anything downstream of that branch. The router
node ALSO resets retrieved_context to its empty default on every turn, before
picking a branch - without that, a chat that used RAG on turn 1 and switched
routes on turn 2 would still be carrying turn 1's stale retrieved_context
into turn 2's prompt, since a plain field only ever changes when the node
that owns it actually runs.

`web_search_requested` (Phase 14.6) is set from the CALLER, not decided by
the router - it's how the frontend's explicit "web search" toggle reaches the
graph. When True, router_node short-circuits straight to route="web_search"
without spending a classification call on it (see router_node.py) - this is
the one route the classifier itself never chooses on its own; it's always an
explicit user override.

`web_search_results` (Phase 18) is the web_search route's own
retrieve-then-generate handoff, mirroring `retrieved_context` exactly but
kept as a SEPARATE field on purpose (Phase 18 doc section 12: RAG and web
search are different systems - private/document knowledge vs. the public
web via Tavily - and merging their state would blur that distinction for no
benefit). app/langgraph/nodes/web_search_node.py (Tavily retrieval) writes
it; web_search_answer_node.py (grounded generation, via the same
Gemini/Groq ModelService normal/RAG use) reads it and clears nothing itself
- like retrieved_context, it's overwritten fresh every turn by the node
that owns it. `web_search_sources` is the citation-only subset (title/url)
of the same Tavily response, set at the same time - unlike Phase 14.6,
citations no longer depend on parsing a model's own tool-use output, since
Tavily returns them directly at retrieval time, before generation even
starts.

`tool_calls_made` (Phase 17) is observability-only, the same role `route`
plays for the router - agent_node.py records which MCP tool(s) it actually
invoked this turn (e.g. ["get_current_weather"]), purely so messages.py can
surface a subtle "used: weather" indicator to the frontend (see
app/langgraph/nodes/agent_node.py) without the frontend needing to parse
message content or know MCP exists. Reset every turn like retrieved_context/
web_search_sources - it's per-turn, not cumulative.

Deliberately NOT storing tool call arguments or raw results here: the
agent-loop's tool_call/result exchanges live only in agent_node.py's local
variables for the duration of one turn, never written to ChatState at all,
so they're never checkpointed - see that module's docstring for why (email
content in particular must not silently become persistent conversation
memory, per the Phase 17 doc's privacy requirements).
"""
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.services.tavily_service import TavilySearchResult
from app.services.vector_store_service import RetrievedChunk

Route = Literal["normal", "rag", "web_search"]


class WebSearchSource(TypedDict):
    """One citation for the current turn's web search reply - title/url
    only, normalized from a TavilySearchResult (see web_search_node.py)."""

    title: str
    url: str


class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    retrieved_context: list[RetrievedChunk]
    web_search_results: list[TavilySearchResult]
    web_search_sources: list[WebSearchSource]
    web_search_requested: bool
    tool_calls_made: list[str]
    route: Route | None
