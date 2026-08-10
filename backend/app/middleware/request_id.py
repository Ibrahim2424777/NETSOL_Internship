"""Per-request correlation ID.

Assigns every request a UUID, makes it available to any log call made while
handling that request (via a contextvar, so no need to thread it through
every function signature), and echoes it back as a response header so a
client can quote it when reporting an issue. Turns "which of these 500
interleaved log lines belongs to the failing request" from a guessing game
into a grep.
"""
import contextvars
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


class RequestIDLogFilter(logging.Filter):
    """Attached to the logging config (see app/config/logging.py) so every
    log record - not just ones inside request handlers - gets a request_id
    attribute the log format string can reference. Records logged outside
    any request (startup/shutdown, background persistence tasks) get "-",
    the contextvar's default, rather than a missing-attribute error.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True
