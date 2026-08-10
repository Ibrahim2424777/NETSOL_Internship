"""Async SQLAlchemy engine and session factory for PostgreSQL.

PostgreSQL is the system's source of truth (see app/redis/client.py for the
cache layer). Every table defined in later phases is reached through the
session produced here.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    # SQL-statement verbosity is controlled by the "sqlalchemy.engine" logger
    # level (see app/config/logging.py), not by echo: passing echo=True makes
    # SQLAlchemy attach its own extra handler with its own format, which
    # duplicates every line already reaching our handler via propagation.
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped database session.

    Route/service code is responsible for committing when it wants a write to
    persist; on an unhandled exception the transaction is rolled back so a
    failed request can never leave a partial write behind.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
