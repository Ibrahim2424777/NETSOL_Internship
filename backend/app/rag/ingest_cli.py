"""Standalone CLI to ingest a document into the RAG vector store.

Run with (from backend/):
    uv run python -m app.rag.ingest_cli [path/to/document.pdf]

Defaults to the bundled fictional test document if no path is given.

Deliberately a CLI script, not an HTTP endpoint (see Phase 12 doc section
17): this phase ships with one fixed document and has no multi-user upload
flow, so an ingestion endpoint would be pure unauthenticated-filesystem-
access attack surface for zero functional gain. Mirrors how Alembic
migrations are already a CLI-driven, developer-run process in this project,
not something triggered over HTTP.

Separate from app/main.py's lifespan - the running app only ever needs a
Retriever (read-only), never the ingestion/embedding-write path.
"""
import asyncio
import logging
import sys
from pathlib import Path

from app.config.logging import configure_logging
from app.config.settings import get_settings
from app.rag.ingestion import ingest_document
from app.services.fastembed_service import FastEmbedService
from app.services.vector_store_service import VectorStoreService

logger = logging.getLogger(__name__)

DEFAULT_DOCUMENT = (
    Path(__file__).resolve().parents[2] / "data" / "documents" / "university_ai_research_handbook.pdf"
)


async def main() -> None:
    configure_logging()
    settings = get_settings()

    doc_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DOCUMENT
    if not doc_path.is_file():
        logger.error("Document not found: %s", doc_path)
        sys.exit(1)

    embedding_cache_dir = str(Path(settings.RAG_VECTOR_DB_PATH).parent / "embedding_cache")
    embedding_service = await FastEmbedService.create(
        model_name=settings.RAG_EMBEDDING_MODEL, cache_dir=embedding_cache_dir
    )
    vector_store = await VectorStoreService.create(
        db_path=settings.RAG_VECTOR_DB_PATH, embedding_service=embedding_service
    )

    count = await ingest_document(
        doc_path,
        vector_store=vector_store,
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
    )
    logger.info("Done: ingested %d chunk(s) from %s into %s", count, doc_path.name, settings.RAG_VECTOR_DB_PATH)


if __name__ == "__main__":
    asyncio.run(main())
