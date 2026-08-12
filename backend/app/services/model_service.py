"""Abstraction over "some LLM that can turn a conversation into a response".

The LangGraph model node (app/langgraph/nodes/model_node.py) depends on this
interface, never on Gemini directly. Swapping providers later means writing a
new ModelService implementation and changing the one place that constructs it
(app/api/deps.py) - the node and graph stay untouched.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import Literal, TypedDict


class ModelTurn(TypedDict):
    """One turn of conversation history, provider-agnostic (not a LangChain
    message and not Gemini's own Content type) so this interface doesn't leak
    either dependency to callers."""

    role: Literal["user", "model"]
    content: str


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
