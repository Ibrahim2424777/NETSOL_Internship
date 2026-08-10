"""Health check endpoint.

Reports process status plus live connectivity to PostgreSQL and Redis. Each
dependency is probed independently and a failure in one is reported, not
raised, so the endpoint still responds (with a "degraded" status) instead of
502-ing when only one backing service is down.
"""
import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession, RedisClient, SettingsDep
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: DbSession,
    redis_client: RedisClient,
    settings: SettingsDep,
) -> HealthResponse:
    try:
        await db.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        logger.exception("Database health check failed")
        database_status = "unavailable"

    try:
        await redis_client.ping()
        redis_status = "ok"
    except Exception:
        logger.exception("Redis health check failed")
        redis_status = "unavailable"

    overall_status = "ok" if database_status == "ok" and redis_status == "ok" else "degraded"

    return HealthResponse(
        status=overall_status,
        environment=settings.ENVIRONMENT,
        version=settings.APP_VERSION,
        database=database_status,
        redis=redis_status,
    )
