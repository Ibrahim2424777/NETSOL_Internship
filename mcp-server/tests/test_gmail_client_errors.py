"""HTTP-level tests for app/email/gmail_client.py - transport failures
(timeout, 401/403/404/429/5xx, malformed JSON) mocked via pytest-httpx,
verifying each is translated into the right EmailError subclass. Token
fetching is monkeypatched directly (not mocked at the HTTP layer) so these
tests are only exercising the Gmail API call itself, not the separate OAuth
token-refresh flow (see test_gmail_auth.py for that).
"""
import httpx
import pytest

from app.email import gmail_client
from app.email.errors import (
    EmailAuthenticationError,
    EmailNotFoundError,
    EmailProviderUnavailableError,
    EmailRateLimitedError,
)


@pytest.fixture(autouse=True)
def fake_access_token(monkeypatch):
    async def fake_get_access_token():
        return "fake-access-token"

    monkeypatch.setattr(gmail_client, "get_access_token", fake_get_access_token)


@pytest.mark.asyncio
async def test_401_raises_authentication_error(httpx_mock):
    httpx_mock.add_response(status_code=401, json={"error": "invalid_grant"})

    with pytest.raises(EmailAuthenticationError):
        await gmail_client.list_message_ids(max_results=5)


@pytest.mark.asyncio
async def test_403_raises_authentication_error(httpx_mock):
    httpx_mock.add_response(status_code=403, json={"error": "insufficient_scope"})

    with pytest.raises(EmailAuthenticationError):
        await gmail_client.list_message_ids(max_results=5)


@pytest.mark.asyncio
async def test_404_raises_not_found_error(httpx_mock):
    httpx_mock.add_response(status_code=404, json={"error": "not found"})

    with pytest.raises(EmailNotFoundError):
        await gmail_client.get_message_full("nonexistent")


@pytest.mark.asyncio
async def test_429_raises_rate_limited_error(httpx_mock):
    httpx_mock.add_response(status_code=429, json={"error": "rate limited"})

    with pytest.raises(EmailRateLimitedError):
        await gmail_client.list_message_ids(max_results=5)


@pytest.mark.asyncio
async def test_server_error_raises_provider_unavailable(httpx_mock):
    httpx_mock.add_response(status_code=500, json={"error": "internal"})

    with pytest.raises(EmailProviderUnavailableError):
        await gmail_client.list_message_ids(max_results=5)


@pytest.mark.asyncio
async def test_timeout_raises_provider_unavailable(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))

    with pytest.raises(EmailProviderUnavailableError):
        await gmail_client.send_message("fake-raw-message")


@pytest.mark.asyncio
async def test_send_message_success(httpx_mock):
    httpx_mock.add_response(status_code=200, json={"id": "msg123", "threadId": "thread123"})

    result = await gmail_client.send_message("fake-raw-message")

    assert result["id"] == "msg123"
