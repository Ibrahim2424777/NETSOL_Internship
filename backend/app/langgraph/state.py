"""Shared state passed between LangGraph nodes.

Every node reads from and writes to this single structure as it flows through
the graph. `messages` is the full conversation for the current thread
(chat_id) as loaded from the checkpointer, plus whatever a node appends -
`add_messages` is a reducer, not a plain field assignment: a node returning
{"messages": [new_message]} appends, it never overwrites what the checkpointer
already loaded. This is what lets callers pass only the new turn's message as
input instead of replaying the whole history on every call.

Future phases extend this — e.g. a `retrieved_context: list[str]` field for
RAG, a `tool_calls` field for tool calling — rather than replacing it, so
existing nodes keep working unchanged when new nodes are added.
"""
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
