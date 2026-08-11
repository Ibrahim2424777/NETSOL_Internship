"""Reusable document retriever: query -> embedding -> similarity search ->
relevant chunks.

Deliberately independent of LangGraph - app/langgraph/nodes/retriever_node.py
is a thin wrapper around this, not the other way around. Phase 14's router
is expected to call this directly for retrieval outside the graph too, per
the Phase 12 spec's requirement to keep retrieval reusable ahead of that.
"""
from app.services.vector_store_service import RetrievedChunk, VectorStoreService


class Retriever:
    def __init__(self, vector_store: VectorStoreService, *, top_k: int, min_score: float = 0.0) -> None:
        self._vector_store = vector_store
        self._top_k = top_k
        self._min_score = min_score

    async def retrieve(self, query: str) -> list[RetrievedChunk]:
        results = await self._vector_store.similarity_search(query, top_k=self._top_k)
        # A vector search always returns its k nearest neighbors, even for a
        # completely unrelated query - filtering by score is what turns
        # "closest anyway" into "actually relevant", which matters both for
        # prompt quality (don't hand Gemini noise) and for source
        # attribution (don't claim a document was used when it wasn't).
        return [chunk for chunk in results if chunk["score"] >= self._min_score]
