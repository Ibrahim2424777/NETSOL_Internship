"""Thin REST client over the Gmail API - same shape as
app/weather/client.py (a plain function per operation, one shared
`_request` helper doing auth/timeout/error translation), not the full
google-api-python-client SDK, for the same "plain HTTP over a heavy
provider SDK" preference this project uses elsewhere (Gemini/Groq/Open-Meteo
are all called directly too).
"""
import logging

import httpx

from app.config import get_settings
from app.email.errors import (
    EmailAuthenticationError,
    EmailNotFoundError,
    EmailProviderUnavailableError,
    EmailRateLimitedError,
)
from app.email.gmail_auth import get_access_token

logger = logging.getLogger(__name__)

_GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


async def _request(method: str, path: str, **kwargs) -> dict:
    settings = get_settings()
    token = await get_access_token()

    try:
        async with httpx.AsyncClient(timeout=settings.EMAIL_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.request(
                method, f"{_GMAIL_API_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
                **kwargs,
            )
    except httpx.TimeoutException as exc:
        raise EmailProviderUnavailableError("Gmail API request timed out.") from exc
    except httpx.HTTPError as exc:
        logger.exception("Gmail API request failed: %s %s", method, path)
        raise EmailProviderUnavailableError("Could not reach Gmail.") from exc

    if response.status_code == 401:
        raise EmailAuthenticationError(
            "Gmail rejected these credentials - the refresh token may be invalid or revoked."
        )
    if response.status_code == 403:
        raise EmailAuthenticationError("Gmail denied this request - check the authorized scopes.")
    if response.status_code == 404:
        raise EmailNotFoundError("The requested email was not found.")
    if response.status_code == 429:
        raise EmailRateLimitedError("Gmail API rate limit hit. Try again shortly.")
    if response.status_code >= 500:
        raise EmailProviderUnavailableError(f"Gmail API returned {response.status_code}.")
    if response.status_code >= 400:
        logger.warning("Unexpected Gmail API status %s: %s", response.status_code, response.text[:300])
        raise EmailProviderUnavailableError(f"Gmail API returned an unexpected {response.status_code}.")

    try:
        return response.json()
    except ValueError as exc:
        raise EmailProviderUnavailableError("Gmail API returned a malformed response.") from exc


async def send_message(raw: str) -> dict:
    return await _request("POST", "/messages/send", json={"raw": raw})


async def list_message_ids(*, max_results: int) -> list[str]:
    data = await _request("GET", "/messages", params={"maxResults": max_results})
    return [m["id"] for m in data.get("messages", []) or []]


async def get_message_metadata(message_id: str) -> dict:
    return await _request(
        "GET", f"/messages/{message_id}",
        params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
    )


async def get_message_full(message_id: str) -> dict:
    return await _request("GET", f"/messages/{message_id}", params={"format": "full"})
