"""The three email MCP tools: send_email, list_recent_emails, read_email.

Only registered onto the server when Gmail is actually configured (see
server.py) - this module still imports cleanly and is fully testable
without credentials (auth/network calls only happen inside the tool
functions themselves, never at import time).
"""
import logging
import re

from app.config import get_settings
from app.email import gmail_client
from app.email.errors import InvalidRecipientError
from app.email.mime import build_raw_message, extract_plain_text_body, parse_message_headers
from app.email.models import EmailContent, EmailSummary, RecentEmailsResult, SendEmailResult

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _looks_like_email(address: str) -> bool:
    return bool(_EMAIL_RE.match(address))


async def send_email(to: str, subject: str, body: str) -> SendEmailResult:
    """Sends an email. `to` may be a real address, or the literal string
    "me" to send to this server's own configured Gmail account (the natural
    resolution for "email me"/"send me..." requests - see README.md's
    "Location handling"-equivalent note for email). Validates the recipient
    looks like a real email address and that subject/body aren't empty
    before ever calling Gmail (Phase 17 doc section 11)."""
    settings = get_settings()

    to = to.strip()
    subject = subject.strip()
    body = body.strip()

    recipient = settings.GMAIL_USER_EMAIL if to.lower() == "me" else to
    if not _looks_like_email(recipient):
        raise InvalidRecipientError(f"{recipient!r} doesn't look like a valid email address.")
    if not subject:
        raise InvalidRecipientError("Subject must not be empty.")
    if not body:
        raise InvalidRecipientError("Body must not be empty.")

    raw = build_raw_message(sender=settings.GMAIL_USER_EMAIL, to=recipient, subject=subject, body=body)
    result = await gmail_client.send_message(raw)

    logger.info("Email sent to %s (message_id=%s) - subject/body not logged", recipient, result.get("id"))
    return SendEmailResult(message_id=result["id"], to=recipient, subject=subject, status="sent")


async def list_recent_emails(limit: int = 10) -> RecentEmailsResult:
    """Lists recent emails as METADATA ONLY (sender, subject, date, message
    ID) - never full bodies, per Phase 17 doc section 13's "do not dump an
    entire inbox" and section 14's "only retrieve the minimum content
    required". Call read_email(message_id) for one message's actual
    content. `limit` is capped server-side regardless of what's requested
    (see EMAIL_LIST_MAX_RESULTS)."""
    settings = get_settings()
    bounded_limit = max(1, min(limit, settings.EMAIL_LIST_MAX_RESULTS))

    ids = await gmail_client.list_message_ids(max_results=bounded_limit)

    summaries: list[EmailSummary] = []
    for message_id in ids:
        metadata = await gmail_client.get_message_metadata(message_id)
        headers = parse_message_headers(metadata)
        summaries.append(
            EmailSummary(
                message_id=message_id, sender=headers["from"], subject=headers["subject"], date=headers["date"],
            )
        )

    return RecentEmailsResult(emails=summaries, count=len(summaries))


async def read_email(message_id: str) -> EmailContent:
    """Retrieves one email's full content by its message ID (from
    list_recent_emails' results - never guess a message ID). Body is
    truncated at EMAIL_BODY_MAX_CHARS if very long."""
    settings = get_settings()

    full = await gmail_client.get_message_full(message_id)
    headers = parse_message_headers(full)
    body = extract_plain_text_body(full.get("payload", {}))

    truncated = len(body) > settings.EMAIL_BODY_MAX_CHARS
    if truncated:
        body = body[: settings.EMAIL_BODY_MAX_CHARS] + "... [truncated]"

    logger.info("Email read: message_id=%s - body content not logged", message_id)
    return EmailContent(
        message_id=message_id, sender=headers["from"], subject=headers["subject"], date=headers["date"],
        body=body, truncated=truncated,
    )


def register_email_tools(mcp) -> None:
    settings = get_settings()

    mcp.tool(
        name="send_email",
        description=(
            "Send an email. `to` should be a real email address, or the literal string \"me\" "
            "to send to the user's own configured email address (use \"me\" whenever the user "
            "says things like 'email me' or 'send me' without naming a specific address). "
            "Always confirm the recipient, subject, and body with the user before calling this "
            "tool if you haven't already gotten their explicit go-ahead in this conversation - "
            "sending an email is irreversible. Returns the sent message's ID on success, or a "
            "clear error (invalid recipient, empty subject/body, authentication failure, etc.)."
        ),
    )(send_email)

    mcp.tool(
        name="list_recent_emails",
        description=(
            f"List the user's most recent emails as metadata only (sender, subject, date, "
            f"message ID) - NOT full content. `limit` defaults to 10, capped at "
            f"{settings.EMAIL_LIST_MAX_RESULTS} regardless of what's requested. Use read_email "
            f"with a message ID from these results to get one email's actual content."
        ),
    )(list_recent_emails)

    mcp.tool(
        name="read_email",
        description=(
            "Retrieve one email's full content (sender, subject, date, plain-text body) by its "
            "message ID - get the message ID from list_recent_emails first, never guess one. "
            f"Long bodies are truncated at {settings.EMAIL_BODY_MAX_CHARS} characters "
            "(see the `truncated` field in the result)."
        ),
    )(read_email)
