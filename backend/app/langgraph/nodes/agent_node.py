"""Agent node (Phase 17) - the "normal" route's destination, replacing plain
model_node.py for that branch only (RAG uses model_node; web_search uses its
own retrieve-then-generate pair, web_search_node.py + web_search_answer_node.py
- see chat_graph.py).

Gives the model access to whatever tools the standalone MCP server
(../mcp-server) currently exposes - weather, and email if configured - via
app/mcp/client.py, and runs the request/execute/respond loop until the
model has a final answer, per the Phase 17 doc's core requirement: the model
decides when a tool is needed, this app never hardcodes "if message contains
X, call tool Y" (section 16).

WHY THIS ISN'T model_node.py WITH TOOLS BOLTED ON: model_node.py streams
token-by-token via generate_stream(). Tool-calling fundamentally can't: you
don't know whether a response will BE a tool call until the model has
finished deciding, so the decision step is a non-streaming
generate_with_tools() call (see model_service.py). Once a final answer is
reached, its text is already complete - _fake_stream() re-chunks it into
small pieces with a short delay between writer() calls so the frontend still
gets a typing-effect UI, but this is not real token streaming from the
provider. This is the one place in the graph that still needs this
trick - web_search_answer_node.py (like model_node.py) streams for real,
since Tavily already did the retrieval before generation ever starts, so
there's no "might this turn into a tool call" ambiguity to wait out there.

PRIVACY: the tool_call/result exchanges that happen mid-loop (e.g. a
send_email call and its result, or an email's content from read_email) are
kept ENTIRELY in this function's local `exchanges` list - never written to
ChatState, never checkpointed. Only the ORIGINAL user message (already in
state["messages"] before this node ever runs) and the model's FINAL
natural-language reply get persisted. This is deliberate, not an oversight:
the Phase 17 doc explicitly requires that email content not automatically
become long-term memory (section 19) - whatever the model chooses to restate
in its own final reply is far more minimal than a raw tool result, and nudged
to actually stay minimal (see WEATHER-only mention in _TOOL_USE_INSTRUCTIONS).
"""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.config import get_stream_writer

from app.langgraph.state import ChatState
from app.mcp.client import MCPClientService
from app.mcp.errors import MCPError, MCPUnavailableError
from app.services.model_service import ModelService, ModelTurn, ToolExchange

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5

# Fake-streaming chunk shape - see module docstring's "WHY" section. Small
# enough to still read as incremental, large enough not to spam the SSE
# connection with hundreds of tiny frames for a long reply.
_FAKE_STREAM_WORDS_PER_CHUNK = 4
_FAKE_STREAM_DELAY_SECONDS = 0.02

_TOOL_USE_INSTRUCTIONS = (
    "Instructions: You have access to tools for checking real weather and (if configured) "
    "sending/reading email - use them whenever they would give a more accurate or current "
    "answer than your own knowledge, rather than guessing. Never invent weather data, email "
    "content, or send-confirmation details. Before calling a tool that sends an email, make "
    "sure the user has clearly asked for it or explicitly confirmed a draft you already "
    "described to them in this conversation - if you haven't already gotten that confirmation, "
    "describe what you would send (recipient, subject, body) and ask first instead of sending."
)


def _to_turn(message: AnyMessage) -> ModelTurn:
    role = "user" if isinstance(message, HumanMessage) else "model"
    content = message.content if isinstance(message.content, str) else str(message.content)
    return {"role": role, "content": content}


def _with_tool_instructions(history: list[ModelTurn]) -> list[ModelTurn]:
    if not history or history[-1]["role"] != "user":
        return history
    augmented = f"{history[-1]['content']}\n\n{_TOOL_USE_INSTRUCTIONS}"
    return [*history[:-1], {"role": "user", "content": augmented}]


async def _fake_stream(text: str, writer: Callable[[str], None]) -> None:
    words = text.split(" ")
    for i in range(0, len(words), _FAKE_STREAM_WORDS_PER_CHUNK):
        chunk = " ".join(words[i : i + _FAKE_STREAM_WORDS_PER_CHUNK])
        if i + _FAKE_STREAM_WORDS_PER_CHUNK < len(words):
            chunk += " "
        writer(chunk)
        await asyncio.sleep(_FAKE_STREAM_DELAY_SECONDS)


def make_agent_node(
    model_service: ModelService, mcp_client: MCPClientService, *, max_history_messages: int
) -> Callable[[ChatState], Awaitable[ChatState]]:
    async def agent_node(state: ChatState) -> ChatState:
        trimmed = state["messages"][-max_history_messages:]
        plain_history = [_to_turn(message) for message in trimmed]

        writer = get_stream_writer()
        tools_used: list[str] = []

        try:
            tools = await mcp_client.list_tools()
        except MCPUnavailableError:
            # Graceful degradation (Phase 17 doc section 21, Test 10): the
            # normal route must keep working even if the MCP server is down
            # - it just can't offer tools this turn. Falls all the way back
            # to plain generate_stream(), which also means real
            # token-by-token streaming for this degraded case, unlike the
            # tool-using path below.
            logger.warning("MCP server unavailable - continuing without tools this turn")
            tools = []

        if not tools:
            # Deliberately NOT using _with_tool_instructions() here - telling
            # the model about tools it isn't actually being offered (no
            # `tools=` param this call) confused at least one Groq model
            # (openai/gpt-oss-120b) into attempting a tool call anyway,
            # which the API then rejects outright ("Tool choice is none,
            # but model called a tool"), turning graceful degradation into
            # a hard failure. Only mention tool use when tools are real.
            chunks: list[str] = []
            async for chunk in model_service.generate_stream(plain_history):
                chunks.append(chunk)
                writer(chunk)
            full_response = "".join(chunks)
            if not full_response:
                raise RuntimeError("Model service returned an empty response")
            return {"messages": [AIMessage(content=full_response)], "tool_calls_made": tools_used}

        history = _with_tool_instructions(plain_history)
        exchanges: list[ToolExchange] = []
        final_text: str | None = None

        for _ in range(MAX_TOOL_ITERATIONS):
            response = await model_service.generate_with_tools(history, tools=tools, exchanges=exchanges)

            if not response["tool_calls"]:
                final_text = response["text"]
                break

            for call in response["tool_calls"]:
                logger.info("agent_node calling MCP tool: %s", call["name"])
                try:
                    result = await mcp_client.call_tool(call["name"], call["arguments"])
                    result_content = json.dumps(result)
                except MCPError as exc:
                    # Fed back to the MODEL as the tool's result, not raised -
                    # letting the model explain the failure in its own words
                    # (Phase 17 doc section 21: "the user should receive a
                    # useful explanation", generated the same natural way as
                    # any other reply, not a hardcoded error string).
                    logger.warning("MCP tool %s failed: %s", call["name"], exc)
                    result_content = json.dumps({"error": str(exc)})

                tools_used.append(call["name"])
                exchanges.append({"tool_call": call, "result_content": result_content})

        if final_text is None:
            # Exhausted MAX_TOOL_ITERATIONS without the model settling on a
            # final answer - a safety cap, not an expected path. Fail the
            # turn cleanly rather than silently returning a truncated/empty
            # reply (same "raise, don't checkpoint a broken turn" reasoning
            # as model_node.py's empty-response check).
            raise RuntimeError("Model did not produce a final response within the tool-calling limit")

        await _fake_stream(final_text, writer)
        return {"messages": [AIMessage(content=final_text)], "tool_calls_made": tools_used}

    return agent_node
