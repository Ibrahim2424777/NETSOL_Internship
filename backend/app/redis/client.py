"""Async Redis client for the conversation/session cache layer.

Redis is never the source of truth for this project (PostgreSQL is — see
app/database/session.py). This client is only ever used for:
  - active conversation cache
  - session cache
  - fast retrieval / performance optimization

A single connection pool is created at import time and shared by every
request; get_redis() hands out a lightweight client bound to that pool and
releases it back when the request finishes.
"""
from collections.abc import AsyncGenerator

from redis.asyncio import ConnectionPool, Redis

from app.config.settings import get_settings

settings = get_settings()

redis_pool = ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    max_connections=20,
)


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding a request-scoped Redis client."""
    client = Redis(connection_pool=redis_pool)
    try:
        yield client
    finally:
        await client.aclose()
