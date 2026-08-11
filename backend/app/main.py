"""Application entry point.

Run with:
    uv run uvicorn app.main:app --reload --loop app.core.event_loop:event_loop_factory

The custom --loop is required on Windows so psycopg (used by the LangGraph
Postgres checkpointer) gets a SelectorEventLoop instead of Uvicorn's default
ProactorEventLoop - see app/core/event_loop.py.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.api.deps import get_model_service
from app.api.v1.router import api_router
from app.config.logging import configure_logging
from app.config.settings import get_settings
from app.database.session import engine
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.rag.retriever import Retriever
from app.redis.client import redis_pool
from app.services.chat_execution_service import ChatExecutionService
from app.services.fastembed_service import FastEmbedService
from app.services.vector_store_service import VectorStoreService

configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


def _checkpointer_conn_string() -> str:
    # AsyncPostgresSaver uses psycopg, not the app's own asyncpg/SQLAlchemy
    # driver - same database, different driver, so the URL scheme needs
    # translating (asyncpg's DSN scheme isn't one psycopg understands).
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s [%s]", settings.APP_NAME, settings.ENVIRONMENT)

    checkpoint_pool = AsyncConnectionPool(
        _checkpointer_conn_string(),
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    await checkpoint_pool.open()
    checkpointer = AsyncPostgresSaver(conn=checkpoint_pool)
    await checkpointer.setup()  # idempotent - safe to run on every startup

    # fastembed's model cache defaults to the OS temp directory, which can be
    # cleared at any time - pinning it next to the vector store keeps a
    # restart from silently turning into a slow re-download.
    embedding_cache_dir = str(Path(settings.RAG_VECTOR_DB_PATH).parent / "embedding_cache")
    embedding_service = await FastEmbedService.create(
        model_name=settings.RAG_EMBEDDING_MODEL, cache_dir=embedding_cache_dir
    )
    vector_store = await VectorStoreService.create(
        db_path=settings.RAG_VECTOR_DB_PATH, embedding_service=embedding_service
    )
    retriever = Retriever(vector_store, top_k=settings.RAG_TOP_K, min_score=settings.RAG_MIN_SCORE)

    app.state.checkpoint_pool = checkpoint_pool
    app.state.chat_execution_service = ChatExecutionService(
        get_model_service(),
        retriever,
        checkpointer=checkpointer,
        max_history_messages=settings.MAX_HISTORY_MESSAGES,
    )

    yield

    logger.info("Shutting down %s", settings.APP_NAME)
    await engine.dispose()
    await redis_pool.disconnect()
    await checkpoint_pool.close()


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort safety net for anything a route didn't already turn into
    an HTTPException. Two jobs: make sure it's actually logged (with a full
    traceback, under our own logger/format - not just whatever Starlette's
    bare default would do), and make sure the client only ever sees a plain,
    generic message - never str(exc), which could echo internal details.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Order matters: the LAST middleware added is the OUTERMOST, so it runs
    # first on the way in and last on the way out. RequestID must be
    # outermost so the request_id it sets is still active for the innermost
    # ones' own logging (RequestLoggingMiddleware) further down the stack -
    # if it were added before RequestLoggingMiddleware, RequestID's context
    # would already be torn down by the time RequestLoggingMiddleware logs.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
