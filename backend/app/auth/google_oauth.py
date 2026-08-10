"""Google OAuth 2.0: exchange an authorization code for Google's tokens, then
verify the ID token Google returns.

This is the ONLY place that talks to Google. The frontend hands us a raw
authorization code obtained from Google's consent redirect; we never trust
anything about the user's identity until we've independently verified it here.
"""
import asyncio
import logging

import httpx
from google.auth.transport import requests as google_auth_transport
from google.oauth2 import id_token as google_id_token

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_VALID_ISSUERS = ("accounts.google.com", "https://accounts.google.com")

# Reused across calls so google-auth's internal cache of Google's public
# signing certs is actually effective, instead of re-fetching them every time.
_google_auth_request = google_auth_transport.Request()


class GoogleOAuthError(Exception):
    """Any failure verifying the user's identity with Google - always
    surfaced to the client as 401, never as a 500."""


async def exchange_code_for_id_token(*, code: str, redirect_uri: str) -> str:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        except httpx.HTTPError as exc:
            raise GoogleOAuthError(f"Could not reach Google's token endpoint: {exc}") from exc

    if response.status_code != 200:
        logger.warning("Google token exchange rejected: %s %s", response.status_code, response.text)
        raise GoogleOAuthError("Google rejected the authorization code")

    id_token_str = response.json().get("id_token")
    if not id_token_str:
        raise GoogleOAuthError("Google's token response did not include an id_token")
    return id_token_str


async def verify_google_id_token(token: str) -> dict:
    """Verifies signature, audience, issuer, and expiry against Google's
    public certs, then returns the token's claims (sub, email, name, picture, ...).

    verify_oauth2_token is a synchronous, blocking call (it may do a network
    fetch for Google's certs), so it's run off the event loop.
    """
    settings = get_settings()
    try:
        claims = await asyncio.to_thread(
            google_id_token.verify_oauth2_token,
            token,
            _google_auth_request,
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise GoogleOAuthError(f"Invalid Google ID token: {exc}") from exc

    if claims.get("iss") not in _VALID_ISSUERS:
        raise GoogleOAuthError("Unexpected token issuer")

    if not claims.get("email_verified", False):
        raise GoogleOAuthError("Google account email is not verified")

    return claims
