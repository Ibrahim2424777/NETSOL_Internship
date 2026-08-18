"""Turns the stored Gmail OAuth refresh token into a fresh access token.

The refresh token itself never expires (unless revoked) and is never sent to
Gmail's data APIs directly - only to Google's token endpoint, to exchange
for a short-lived access token. See scripts/gmail_authorize.py for the
one-time interactive flow that produces the refresh token in the first
place, and README.md's "Email (Gmail)" section for the required scopes.
"""
import asyncio
import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.config import get_settings
from app.email.errors import EmailAuthenticationError, EmailNotConfiguredError

logger = logging.getLogger(__name__)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Cached across calls within this process so a fresh access token isn't
# fetched from Google on every single tool call - refresh() only actually
# hits the network when the cached token is missing/expired (Credentials.valid
# checks expiry locally first).
_cached_credentials: Credentials | None = None


def _build_credentials() -> Credentials:
    settings = get_settings()
    if not settings.email_configured:
        raise EmailNotConfiguredError(
            "Gmail is not configured on this server - GMAIL_CLIENT_ID/GMAIL_CLIENT_SECRET/"
            "GMAIL_REFRESH_TOKEN/GMAIL_USER_EMAIL must be set (see README.md's Email section "
            "and scripts/gmail_authorize.py for the one-time setup)."
        )
    return Credentials(
        token=None,
        refresh_token=settings.GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GMAIL_CLIENT_ID,
        client_secret=settings.GMAIL_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )


async def get_access_token() -> str:
    global _cached_credentials

    if _cached_credentials is None:
        _cached_credentials = _build_credentials()

    if not _cached_credentials.valid:
        try:
            # Credentials.refresh() is a synchronous (blocking, `requests`-based)
            # network call - run it off the event loop rather than blocking
            # every other in-flight request on this server.
            await asyncio.to_thread(_cached_credentials.refresh, Request())
        except Exception as exc:
            logger.exception("Gmail token refresh failed")
            raise EmailAuthenticationError(
                "Gmail authentication failed - the stored refresh token may be invalid or "
                "revoked. Re-run scripts/gmail_authorize.py to re-authorize."
            ) from exc

    return _cached_credentials.token
