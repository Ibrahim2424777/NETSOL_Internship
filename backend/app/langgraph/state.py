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
explicit user override. See app/langgraph/nodes/web_search_node.py for how
that route's actual response generation works - unlike RAG/sports before it,
the web_search branch does NOT converge on the shared model node, since
Groq's compound-mini generates the final grounded answer itself in one step
rather than retrieving-then-generating.

Future phases extend this further - e.g. a `tool_calls` field for tool
calling - rather than replacing it, so existing nodes keep working unchanged
when new nodes are added.
"""
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.services.vector_store_service import RetrievedChunk

Route = Literal["normal", "rag", "web_search"]


class WebSearchSource(TypedDict):
    """One citation Groq's compound-mini search tool surfaced for the
    current turn - see web_search_node.py's _extract_sources."""

    title: str
    url: str


class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    retrieved_context: list[RetrievedChunk]
    web_search_sources: list[WebSearchSource]
    web_search_requested: bool
    route: Route | None
