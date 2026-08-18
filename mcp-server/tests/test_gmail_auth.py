"""Tests for app/email/gmail_auth.py's own error handling - separate from
gmail_client tests since this module owns the module-level credentials
cache, which needs resetting between tests."""
import pytest

from app.email import gmail_auth
from app.email.errors import EmailNotConfiguredError


@pytest.fixture(autouse=True)
def reset_credentials_cache():
    gmail_auth._cached_credentials = None
    yield
    gmail_auth._cached_credentials = None


@pytest.mark.asyncio
async def test_get_access_token_raises_not_configured_when_unset(monkeypatch):
    monkeypatch.setattr(gmail_auth, "get_settings", lambda: type(
        "S", (), {
            "email_configured": False,
            "GMAIL_CLIENT_ID": "", "GMAIL_CLIENT_SECRET": "", "GMAIL_REFRESH_TOKEN": "", "GMAIL_USER_EMAIL": "",
        },
    )())

    with pytest.raises(EmailNotConfiguredError):
        await gmail_auth.get_access_token()
