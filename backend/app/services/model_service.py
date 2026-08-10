"""Abstraction over "some LLM that can turn a conversation into a response".

The LangGraph model node (app/langgraph/nodes/model_node.py) depends on this
interface, never on Gemini directly. Swapping providers later means writing a
new ModelService implementation and changing the one place that constructs it
(app/api/deps.py) - the node and graph stay untouched.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal, TypedDict


class ModelTurn(TypedDict):
    """One turn of conversation history, provider-agnostic (not a LangChain
    message and not Gemini's own Content type) so this interface doesn't leak
    either dependency to callers."""

    role: Literal["user", "model"]
    content: str


class ModelService(ABC):
    @abstractmethod
    async def generate(self, history: list[ModelTurn]) -> str:
        """Given the conversation so far (oldest first, ending with the
        latest user turn), return the model's full text response."""
        raise NotImplementedError

    @abstractmethod
    def generate_stream(self, history: list[ModelTurn]) -> AsyncIterator[str]:
        """Given the conversation so far, yield the response incrementally as
        text chunks."""
        raise NotImplementedError
