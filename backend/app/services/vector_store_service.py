"""Local, persistent vector storage for document RAG, backed by LanceDB.

LanceDB is an embedded (no server process), file-backed vector database -
`RAG_VECTOR_DB_PATH` is just a directory on disk, so this survives backend
restarts on its own without any extra infrastructure, and is a storage layer
entirely separate from PostgreSQL and Redis (see app/config/settings.py's
RAG section for why: PostgreSQL/Redis keep their existing responsibilities
unchanged, this is RAG-specific storage).

Chosen over Chroma (the doc's suggested example) specifically for
dependency weight: Chroma's default install pulls in a Kubernetes client,
gRPC, and OpenTelemetry (baggage from its optional server mode, unused
here) - 52 packages vs LanceDB's 9 for equivalent embedded/persistent
local functionality, verified via a dry-run install comparison.
"""
import asyncio
import uuid
from typing import TypedDict

import lancedb
from lancedb.pydantic import LanceModel, Vector

from app.services.embedding_service import EmbeddingService

_TABLE_NAME = "document_chunks"


class IngestChunk(TypedDict):
    """One chunk about to be embedded and stored - produced by the ingestion
    pipeline (app/rag/ingestion.py), not yet carrying a vector or score."""

    chunk_id: str
    content: str
    source: str
    page: int | None


class RetrievedChunk(TypedDict):
    """One chunk returned by a similarity search - what the retriever node
    puts into ChatState.retrieved_context and, eventually, what gets shown
    to the user as a source."""

    chunk_id: str
    content: str
    source: str
    page: int | None
    score: float


def _make_schema(dimension: int) -> type[LanceModel]:
    # Built dynamically because the embedding dimension depends on
    # RAG_EMBEDDING_MODEL (384 for the default BGE-small, but not every
    # embedding model uses that dimension) - LanceModel needs a fixed-size
    # Vector(dimension) at class-definition time, so this can't be a single
    # module-level class.
    class ChunkSchema(LanceModel):
        chunk_id: str
        content: str
        source: str
        page: int
        vector: Vector(dimension)  # type: ignore[valid-type]

    return ChunkSchema


class VectorStoreService:
    def __init__(self, *, db_path: str, embedding_service: EmbeddingService, dimension: int) -> None:
        self._db_path = db_path
        self._embedding_service = embedding_service
        self._schema = _make_schema(dimension)
        self._db = lancedb.connect(db_path)

    @classmethod
    async def create(cls, *, db_path: str, embedding_service: EmbeddingService) -> "VectorStoreService":
        """Determines the embedding dimension by actually embedding a probe
        string, rather than hardcoding a number tied to one specific
        RAG_EMBEDDING_MODEL - the schema then stays correct regardless of
        which model is configured."""
        probe = await embedding_service.embed_query("dimension probe")
        return cls(db_path=db_path, embedding_service=embedding_service, dimension=len(probe))

    def _get_or_create_table(self):
        return self._db.create_table(_TABLE_NAME, schema=self._schema, exist_ok=True)

    async def replace_source(self, source: str, chunks: list[IngestChunk]) -> int:
        """Ingestion is idempotent per source: existing chunks for this
        source are deleted before the new ones are inserted, so re-running
        ingestion after editing a document doesn't accumulate duplicates."""
        if not chunks:
            return 0

        vectors = await self._embedding_service.embed_documents([c["content"] for c in chunks])
        records = [
            {
                "chunk_id": chunk["chunk_id"],
                "content": chunk["content"],
                "source": chunk["source"],
                "page": chunk["page"] if chunk["page"] is not None else -1,
                "vector": vector,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        def _write() -> int:
            table = self._get_or_create_table()
            # SQL-style string literal, not a parameterized query - LanceDB's
            # delete() only accepts a filter expression string. `source` is
            # always an internally-controlled filename from the ingestion
            # CLI today, never user input, but escaping it is cheap and
            # keeps this safe if that ever changes.
            escaped_source = source.replace("'", "''")
            table.delete(f"source = '{escaped_source}'")
            table.add(records)
            return len(records)

        return await asyncio.to_thread(_write)

    async def similarity_search(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        query_vector = await self._embedding_service.embed_query(query)

        def _search() -> list[RetrievedChunk]:
            if _TABLE_NAME not in self._db.table_names():
                return []  # nothing ingested yet - RAG gracefully no-ops
            table = self._get_or_create_table()
            rows = (
                table.search(query_vector)
                .metric("cosine")
                .limit(top_k)
                .to_list()
            )
            return [
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    content=row["content"],
                    source=row["source"],
                    page=row["page"] if row["page"] != -1 else None,
                    # LanceDB returns cosine *distance* (0 = identical); score
                    # is the more intuitive "higher is more relevant" form.
                    score=1.0 - row["_distance"],
                )
                for row in rows
            ]

        return await asyncio.to_thread(_search)


def new_chunk_id(source: str, page: int | None, index: int) -> str:
    return f"{source}:{page if page is not None else 'x'}:{index}:{uuid.uuid4().hex[:8]}"
