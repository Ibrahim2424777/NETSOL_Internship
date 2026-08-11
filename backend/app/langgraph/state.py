"""Shared state passed between LangGraph nodes.

Every node reads from and writes to this single structure as it flows through
the graph. `messages` is the full conversation for the current thread
(chat_id) as loaded from the checkpointer, plus whatever a node appends -
`add_messages` is a reducer, not a plain field assignment: a node returning
{"messages": [new_message]} appends, it never overwrites what the checkpointer
already loaded. This is what lets callers pass only the new turn's message as
input instead of replaying the whole history on every call.

`retrieved_context` (Phase 12) is a plain field with no reducer - each run of
the retriever node OVERWRITES it with this turn's search results, unlike
`messages`. That's deliberate: retrieval is per-question, not cumulative
conversation history. It still gets checkpointed as part of the overall
state (LangGraph checkpoints the whole dict), but the retriever node always
overwrites it before the model node reads it, so a stale value from a
previous turn is never actually seen. Conversational memory (`messages`,
Phase 11) and document retrieval (`retrieved_context`, Phase 12) stay two
separate mechanisms solving two different problems - see the model node for
where they're combined into one prompt.

Future phases extend this further - e.g. a `tool_calls` field for tool
calling - rather than replacing it, so existing nodes keep working unchanged
when new nodes are added.
"""
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.services.vector_store_service import RetrievedChunk


class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    retrieved_context: list[RetrievedChunk]
