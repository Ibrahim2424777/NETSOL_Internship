"""Abstraction over "some LLM that can turn a conversation into a response".

The LangGraph model node (app/langgraph/nodes/model_node.py) depends on this
interface, never on Gemini directly. Swapping providers later means writing a
new ModelService implementation and changing the one place that constructs it
(app/api/deps.py) - the node and graph stay untouched.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import Literal, NotRequired, TypedDict


class ModelTurn(TypedDict):
    """One turn of conversation history, provider-agnostic (not a LangChain
    message and not Gemini's own Content type) so this interface doesn't leak
    either dependency to callers."""

    role: Literal["user", "model"]
    content: str


class ToolSpec(TypedDict):
    """One tool definition offered to the model, in plain JSON-Schema form -
    provider-agnostic on purpose (Phase 17): both Gemini's FunctionDeclaration
    and Groq's OpenAI-style `tools=[...]` accept a standard JSON Schema
    `parameters` object directly (verified live against both installed SDKs -
    neither needed any reshaping), so this is really just "whatever MCP's
    tools/list already returns", passed straight through with no per-provider
    translation layer to maintain."""

    name: str
    description: str
    parameters: dict


class ToolCall(TypedDict):
    """One tool invocation the model is requesting."""

    id: str
    name: str
    arguments: dict
    # Opaque, provider-specific continuation data a provider may need back
    # on the NEXT generate_with_tools() call to correctly continue this
    # exact tool-calling turn - e.g. Gemini's `thought_signature` (a
    # "thinking" model's internal reasoning trace; required on function-call
    # replies for multi-step tool use per Gemini's own docs, discovered live
    # when a 2-tool-offered, 2+ iteration loop failed with "Function call is
    # missing a thought_signature" - a single-exchange test earlier hadn't
    # exercised this path). Absent/ignored for providers with no equivalent
    # concept (Groq never sets or reads this) - this is exactly the "isolate
    # the difference inside the provider abstraction" the Phase 17 doc asks
    # for (section 17), rather than leaking Gemini-specific shape into
    # agent_node.py or the other provider's implementation.
    provider_data: NotRequired[dict]


class ToolExchange(TypedDict):
    """One completed (tool call -> result) pair from earlier in the CURRENT
    turn's tool-calling loop - see ModelService.generate_with_tools. The loop
    itself (call model -> execute requested tool(s) -> call model again with
    results) lives in app code (app/langgraph/nodes/agent_node.py), not in
    any provider class, since executing an MCP tool call requires the MCP
    client, which providers have no business knowing about. `result_content`
    is a JSON string (or plain text) - already-serialized so every provider
    implementation treats it identically regardless of what the tool
    actually returned."""

    tool_call: ToolCall
    result_content: str


class ModelToolResponse(TypedDict):
    """Result of one generate_with_tools() call. Exactly one of the two
    fields is meaningful: `tool_calls` non-empty means the model wants to
    call tool(s) before it can answer (text is typically empty/None then);
    `tool_calls` empty means `text` is the model's final answer."""

    text: str | None
    tool_calls: list[ToolCall]


class SearchCitation(TypedDict):
    """A citation a provider's own built-in search/tool-use surfaced while
    generating a response (Phase 14.6, e.g. Groq's compound models) - kept
    provider-agnostic (not tied to Groq's specific tool-call shape) so
    generate()/generate_stream()'s on_search_result callback stays a generic
    interface concept, not a Groq-specific bolt-on. Implementations with no
    built-in search (Gemini, plain Groq chat models) simply never call it."""

    title: str
    url: str


class ProviderUnavailableError(Exception):
    """Raised by a ModelService implementation to signal a TRANSIENT,
    provider-level failure - rate limit, quota exhausted, service
    unavailable, timeout - as opposed to a request-specific failure (bad
    prompt, safety block, malformed response). This is the one thing every
    provider implementation classifies for itself (what a 429 looks like on
    Gemini vs. Groq is provider-specific knowledge that belongs in that
    provider's own service class - see gemini_service.py/groq_service.py),
    but the distinction itself is provider-agnostic: it's the only signal
    FallbackModelService (Phase 14.5) acts on to decide whether trying a
    second provider is appropriate. Anything else - including bugs in our
    own code - must surface as a provider-specific exception instead, so a
    fallback attempt never masks a real application error."""


class ModelService(ABC):
    @abstractmethod
    async def generate(
        self,
        history: list[ModelTurn],
        *,
        on_search_result: Callable[[SearchCitation], None] | None = None,
    ) -> str:
        """Given the conversation so far (oldest first, ending with the
        latest user turn), return the model's full text response.

        on_search_result is called once per citation IF this provider does
        its own search/tool use while generating (see SearchCitation) -
        providers without that capability simply never call it. This is
        metadata about the response, never part of the returned text."""
        raise NotImplementedError

    @abstractmethod
    def generate_stream(
        self,
        history: list[ModelTurn],
        *,
        on_search_result: Callable[[SearchCitation], None] | None = None,
    ) -> AsyncIterator[str]:
        """Given the conversation so far, yield the response incrementally as
        text chunks. See generate()'s on_search_result docstring - same
        contract, called as citations are discovered mid-stream rather than
        all at once."""
        raise NotImplementedError

    @abstractmethod
    async def classify(self, history: list[ModelTurn], *, instructions: str, choices: list[str]) -> str:
        """Structured single-label classification over the conversation so
        far, constrained to return exactly one of `choices` - used by the
        LangGraph router node (app/langgraph/nodes/router_node.py), not a
        general-purpose method. Deliberately generic (no routing-specific
        knowledge here): `instructions` and `choices` are supplied by the
        caller, so this interface stays meaningful for any future
        classification need, not just routing.

        A dedicated method rather than reusing generate() - classification
        wants a structured/constrained response (so the result is always
        one of `choices`, never free text to parse), which is a materially
        different request shape from open-ended generation."""
        raise NotImplementedError

    @abstractmethod
    async def generate_with_tools(
        self,
        history: list[ModelTurn],
        *,
        tools: list[ToolSpec],
        exchanges: list[ToolExchange] | None = None,
    ) -> ModelToolResponse:
        """One step of a tool-calling turn (Phase 17) - used by
        app/langgraph/nodes/agent_node.py's loop, never called directly by a
        route that doesn't need tools (RAG/web_search keep using plain
        generate_stream()).

        `history` is the prior conversation, exactly like generate()'s.
        `tools` are the MCP-discovered tool definitions to offer the model
        this call. `exchanges` are this TURN's tool_call/result pairs
        completed so far (empty on the loop's first call) - each
        implementation is responsible for translating history + exchanges
        into its own native multi-turn tool-calling format (e.g. Gemini's
        function_call/function_response Content parts, Groq's
        assistant/tool role messages); callers never see that shape.

        Deliberately non-streaming - the model's "should I call a tool"
        decision isn't shown to the user anyway, only the eventual final
        text is (see agent_node.py for how that's still delivered
        incrementally to the client)."""
        raise NotImplementedError
