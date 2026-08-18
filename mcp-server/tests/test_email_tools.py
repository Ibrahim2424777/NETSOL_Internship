"""Unit tests for app/email/tools.py's business logic - gmail_client calls
are faked via monkeypatch, so these run with no real Gmail credentials and
no network (this repo has none configured yet - see
scripts/gmail_authorize.py)."""
import pytest

from app.email import tools
from app.email.errors import InvalidRecipientError


@pytest.mark.asyncio
async def test_send_email_resolves_me_to_configured_address(monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: type(
        "S", (), {"GMAIL_USER_EMAIL": "owner@example.com", "EMAIL_LIST_MAX_RESULTS": 25, "EMAIL_BODY_MAX_CHARS": 4000},
    )())

    captured = {}

    async def fake_send_message(raw):
        captured["raw"] = raw
        return {"id": "msg123"}

    monkeypatch.setattr(tools.gmail_client, "send_message", fake_send_message)

    result = await tools.send_email("me", "Weather update", "It's 34C in Multan.")

    assert result.to == "owner@example.com"
    assert result.message_id == "msg123"
    assert result.status == "sent"
    assert "raw" in captured


@pytest.mark.asyncio
async def test_send_email_to_explicit_address(monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: type(
        "S", (), {"GMAIL_USER_EMAIL": "owner@example.com", "EMAIL_LIST_MAX_RESULTS": 25, "EMAIL_BODY_MAX_CHARS": 4000},
    )())

    async def fake_send_message(raw):
        return {"id": "msg456"}

    monkeypatch.setattr(tools.gmail_client, "send_message", fake_send_message)

    result = await tools.send_email("friend@example.com", "Hi", "Hello there")

    assert result.to == "friend@example.com"


@pytest.mark.asyncio
async def test_send_email_rejects_invalid_recipient(monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: type(
        "S", (), {"GMAIL_USER_EMAIL": "owner@example.com"},
    )())

    with pytest.raises(InvalidRecipientError, match="valid email address"):
        await tools.send_email("not-an-email", "Subject", "Body")


@pytest.mark.asyncio
async def test_send_email_rejects_empty_subject(monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: type(
        "S", (), {"GMAIL_USER_EMAIL": "owner@example.com"},
    )())

    with pytest.raises(InvalidRecipientError, match="Subject"):
        await tools.send_email("friend@example.com", "   ", "Body")


@pytest.mark.asyncio
async def test_send_email_rejects_empty_body(monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: type(
        "S", (), {"GMAIL_USER_EMAIL": "owner@example.com"},
    )())

    with pytest.raises(InvalidRecipientError, match="Body"):
        await tools.send_email("friend@example.com", "Subject", "")


@pytest.mark.asyncio
async def test_list_recent_emails_returns_metadata_only(monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: type(
        "S", (), {"EMAIL_LIST_MAX_RESULTS": 25},
    )())

    async def fake_list_message_ids(*, max_results):
        assert max_results == 3
        return ["id1", "id2", "id3"]

    async def fake_get_message_metadata(message_id):
        return {
            "payload": {
                "headers": [
                    {"name": "From", "value": f"sender-{message_id}@example.com"},
                    {"name": "Subject", "value": f"Subject {message_id}"},
                    {"name": "Date", "value": "Mon, 17 Aug 2026 10:00:00 +0000"},
                ]
            }
        }

    monkeypatch.setattr(tools.gmail_client, "list_message_ids", fake_list_message_ids)
    monkeypatch.setattr(tools.gmail_client, "get_message_metadata", fake_get_message_metadata)

    result = await tools.list_recent_emails(limit=3)

    assert result.count == 3
    assert result.emails[0].message_id == "id1"
    assert result.emails[0].sender == "sender-id1@example.com"
    assert result.emails[0].subject == "Subject id1"


@pytest.mark.asyncio
async def test_list_recent_emails_caps_limit_server_side(monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: type(
        "S", (), {"EMAIL_LIST_MAX_RESULTS": 5},
    )())

    async def fake_list_message_ids(*, max_results):
        assert max_results == 5  # requested 100, capped to the settings max of 5
        return []

    monkeypatch.setattr(tools.gmail_client, "list_message_ids", fake_list_message_ids)

    result = await tools.list_recent_emails(limit=100)

    assert result.count == 0


@pytest.mark.asyncio
async def test_read_email_extracts_body_and_headers(monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: type(
        "S", (), {"EMAIL_BODY_MAX_CHARS": 4000},
    )())

    async def fake_get_message_full(message_id):
        return {
            "payload": {
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "Subject", "value": "Hello"},
                    {"name": "Date", "value": "Mon, 17 Aug 2026 10:00:00 +0000"},
                ],
                "mimeType": "text/plain",
                "body": {"data": "SGVsbG8gd29ybGQ="},  # "Hello world"
            }
        }

    monkeypatch.setattr(tools.gmail_client, "get_message_full", fake_get_message_full)

    result = await tools.read_email("msg1")

    assert result.sender == "sender@example.com"
    assert result.subject == "Hello"
    assert result.body == "Hello world"
    assert result.truncated is False


@pytest.mark.asyncio
async def test_read_email_truncates_long_body(monkeypatch):
    import base64

    monkeypatch.setattr(tools, "get_settings", lambda: type(
        "S", (), {"EMAIL_BODY_MAX_CHARS": 10},
    )())

    long_text = "x" * 500
    encoded = base64.urlsafe_b64encode(long_text.encode()).decode()

    async def fake_get_message_full(message_id):
        return {
            "payload": {
                "headers": [],
                "mimeType": "text/plain",
                "body": {"data": encoded},
            }
        }

    monkeypatch.setattr(tools.gmail_client, "get_message_full", fake_get_message_full)

    result = await tools.read_email("msg1")

    assert result.truncated is True
    assert result.body.endswith("... [truncated]")
    assert len(result.body) < 500
