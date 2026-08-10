"""Logging configuration.

configure_logging() must be called once, before the FastAPI app is created,
so every logger obtained afterwards (via logging.getLogger(__name__)) inherits
a consistent format and level.
"""
import logging.config

from app.config.settings import get_settings


def configure_logging() -> None:
    settings = get_settings()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)-8s | %(request_id)s | %(name)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            },
            "filters": {
                # Adds the request_id field the format string above
                # references - see app/middleware/request_id.py for what
                # populates it (and why every log record gets one, even
                # outside a request).
                "request_id": {"()": "app.middleware.request_id.RequestIDLogFilter"},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "handlers": ["console"],
                "level": settings.LOG_LEVEL,
            },
            "loggers": {
                # Uvicorn's own loggers are reconfigured to match our format
                # instead of using their default output.
                "uvicorn": {"level": settings.LOG_LEVEL, "propagate": True},
                "uvicorn.error": {"level": settings.LOG_LEVEL, "propagate": True},
                "uvicorn.access": {"level": settings.LOG_LEVEL, "propagate": True},
                # The engine is created with echo left at its default (False)
                # specifically so this is the only thing controlling SQL
                # statement visibility - see app/database/session.py.
                "sqlalchemy.engine": {"level": "INFO" if settings.DEBUG else "WARNING"},
            },
        }
    )
