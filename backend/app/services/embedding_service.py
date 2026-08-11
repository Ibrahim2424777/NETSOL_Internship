"""Abstraction over "some model that turns text into vectors".

Mirrors app/services/model_service.py's pattern: the RAG layer (retriever,
ingestion pipeline, vector store) depends only on this interface, never on
fastembed directly. Swapping embedding providers later means writing a new
EmbeddingService implementation and changing the one place that constructs it
(app/api/deps.py) - nothing else in the RAG code needs to change.

Documents and queries are embedded through separate methods rather than one
generic embed() because some embedding models (including the default one
used here, BAAI/bge-small-en-v1.5) are asymmetric: they expect a different
instruction prefix for "things being indexed" versus "the question searching
for them," and produce measurably worse retrieval quality if that
distinction is dropped.
"""
from abc import ABC, abstractmethod


class EmbeddingService(ABC):
    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of chunks being indexed into the vector store."""
        raise NotImplementedError

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        raise NotImplementedError
