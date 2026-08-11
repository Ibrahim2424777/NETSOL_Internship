"""fastembed-backed EmbeddingService.

fastembed runs a quantized ONNX model on CPU - no PyTorch, no GPU, no
external API call, no per-request cost. Chosen over sentence-transformers
specifically to avoid pulling in PyTorch (600MB+) for a portfolio project
that only ever runs this on CPU - same reasoning that ruled out the
Redis-backed LangGraph checkpointer in Phase 11 in favor of the lighter
Postgres one.

Loading the ONNX model is a blocking, potentially slow (first run downloads
~130MB from Hugging Face, cached locally after) operation - `create()` is an
async factory that runs it in a thread rather than blocking the event loop
in a plain __init__, so this can be awaited from FastAPI's lifespan the same
way the Phase 11 checkpointer's async setup is.
"""
import asyncio
import logging

from fastembed import TextEmbedding

from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class FastEmbedService(EmbeddingService):
    def __init__(self, model: TextEmbedding) -> None:
        self._model = model

    @classmethod
    async def create(cls, *, model_name: str, cache_dir: str) -> "FastEmbedService":
        # Without an explicit cache_dir, fastembed caches the ~130MB ONNX
        # model under the OS temp directory, which can be cleared at any
        # time (e.g. on reboot) - that would silently turn every restart
        # into a slow re-download instead of an instant cache hit.
        logger.info("Loading embedding model %s (cached after first run)", model_name)
        model = await asyncio.to_thread(
            TextEmbedding, model_name=model_name, cache_dir=cache_dir
        )
        return cls(model)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = await asyncio.to_thread(lambda: list(self._model.embed(texts)))
        return [vector.tolist() for vector in vectors]

    async def embed_query(self, text: str) -> list[float]:
        vectors = await asyncio.to_thread(lambda: list(self._model.query_embed([text])))
        return vectors[0].tolist()
