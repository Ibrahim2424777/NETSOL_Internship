"""Document ingestion pipeline: PDF -> text extraction -> chunking ->
embedding -> vector store.

Deliberately separate from the chat request path
(app/services/chat_execution_service.py) - this runs once, ahead of time,
via app/rag/ingest_cli.py, never per chat request. Embeddings are generated
here, at ingestion time, and never regenerated when a user asks a question -
the retriever (app/rag/retriever.py) only ever embeds the query.
"""
import logging
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.services.vector_store_service import IngestChunk, VectorStoreService, new_chunk_id

logger = logging.getLogger(__name__)


def load_pdf_pages(path: Path) -> list[tuple[int, str]]:
    """Returns (page_number, text) for each non-empty page. Page numbers are
    1-indexed so they match how a human would actually cite a page."""
    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if text and text.strip():
            pages.append((index, text))
    return pages


def chunk_pages(
    pages: list[tuple[int, str]], *, source: str, chunk_size: int, chunk_overlap: int
) -> list[IngestChunk]:
    """Recursive/text-aware chunking (paragraph -> sentence -> word
    boundaries, in that preference order) applied per-page rather than to
    the whole document text at once, so every chunk keeps an accurate page
    number instead of one spanning a page boundary."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks: list[IngestChunk] = []
    for page_number, text in pages:
        for index, piece in enumerate(splitter.split_text(text)):
            chunks.append(
                IngestChunk(
                    chunk_id=new_chunk_id(source, page_number, index),
                    content=piece,
                    source=source,
                    page=page_number,
                )
            )
    return chunks


async def ingest_document(
    path: Path,
    *,
    vector_store: VectorStoreService,
    chunk_size: int,
    chunk_overlap: int,
) -> int:
    source = path.name
    pages = load_pdf_pages(path)
    if not pages:
        raise ValueError(f"No extractable text found in {path}")

    chunks = chunk_pages(pages, source=source, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    count = await vector_store.replace_source(source, chunks)
    logger.info("Ingested %d chunks from %s (%d pages)", count, source, len(pages))
    return count
