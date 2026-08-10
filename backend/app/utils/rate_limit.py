"""Redis-backed fixed-window rate limiting.

Deliberately a simple fixed window, not a precise sliding-window
implementation - this exists to blunt credential-stuffing/brute-force abuse
on the auth endpoints (flagged as a known gap back when auth was first
built), not to meter billable usage. Redis's INCR is atomic, so concurrent
requests can't under-count each other; the only race is between the first
INCR in a new window and the EXPIRE that follows it, whose worst case is
that one window runs marginally long - not a real concern at this scale.
"""
import logging

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from app.redis.client import get_redis

logger = logging.getLogger(__name__)


def rate_limiter(*, limit: int, window_seconds: int, bucket: str):
    """Returns a FastAPI dependency enforcing `limit` requests per
    `window_seconds` per client IP. `bucket` namespaces the counter so
    different endpoints don't share one budget.

    Assumes requests reach this process directly (request.client.host is the
    real caller) - a deployment behind a reverse proxy would need this to
    read X-Forwarded-For instead, from a trusted proxy, once one exists.
    """

    async def dependency(request: Request, redis_client: Redis = Depends(get_redis)) -> None:
        client_host = request.client.host if request.client else "unknown"
        key = f"rate_limit:{bucket}:{client_host}"
        try:
            current = await redis_client.incr(key)
            if current == 1:
                await redis_client.expire(key, window_seconds)
        except Exception:
            # Redis being unavailable degrades to "not rate limited", not a
            # broken endpoint - Redis is a performance layer in this project,
            # never a hard dependency for correctness (see app/redis/chat_cache.py).
            logger.warning("Rate limiter could not reach Redis; allowing request through", exc_info=True)
            return

        if current > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )

    return dependency
