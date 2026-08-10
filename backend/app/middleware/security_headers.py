"""Baseline security response headers.

This API only ever returns JSON or an SSE stream, never HTML it renders
itself, so a Content-Security-Policy header (which mainly governs page
content - scripts, styles, frames) isn't meaningful here; that belongs on
the frontend's own hosting layer instead. What's added here is the smaller
set of headers that make sense for any HTTP API regardless of what it returns.
"""
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config.settings import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # Stops a browser from trying to "helpfully" guess a different
        # content type than what we declared (a vector for some XSS/MIME
        # confusion attacks).
        response.headers["X-Content-Type-Options"] = "nosniff"
        # This API is never meant to be framed/embedded.
        response.headers["X-Frame-Options"] = "DENY"
        # Don't leak the full referring URL (which can contain tokens/ids in
        # query strings) to third parties; still allow it same-origin.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if get_settings().ENVIRONMENT == "production":
            # Only meaningful over HTTPS - conditional on environment so it's
            # not sent for plain-http local development.
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        return response
