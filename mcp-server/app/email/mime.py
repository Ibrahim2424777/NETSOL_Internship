"""MIME construction (outgoing) and parsing (incoming) for Gmail API
messages - Gmail's REST API sends/receives raw base64url-encoded RFC 2822
messages, not a simple JSON body/subject shape.
"""
import base64
import re
from email.message import EmailMessage


def build_raw_message(*, sender: str, to: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def parse_message_headers(message: dict) -> dict[str, str]:
    """Extracts From/Subject/Date from a Gmail API message resource's
    payload.headers list (present in both "metadata" and "full" format
    responses)."""
    headers = message.get("payload", {}).get("headers", []) or []
    by_name = {h["name"].lower(): h["value"] for h in headers}
    return {
        "from": by_name.get("from", ""),
        "subject": by_name.get("subject", "(no subject)"),
        "date": by_name.get("date", ""),
    }


def _decode_body_data(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _find_part(payload: dict, mime_type: str) -> str | None:
    if payload.get("mimeType") == mime_type:
        data = payload.get("body", {}).get("data")
        if data:
            return _decode_body_data(data)
    for sub_part in payload.get("parts", []) or []:
        found = _find_part(sub_part, mime_type)
        if found is not None:
            return found
    return None


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_plain_text_body(payload: dict) -> str:
    """Walks a "full"-format Gmail message's MIME tree - prefers a
    text/plain part; falls back to a crude tag-strip of text/html if that's
    all the message has (HTML-only emails are common), rather than pulling
    in a full HTML-parsing dependency for what only needs to be readable
    plain text for the model, not a faithful render."""
    plain = _find_part(payload, "text/plain")
    if plain is not None:
        return plain.strip()

    html = _find_part(payload, "text/html")
    if html is not None:
        return _strip_html(html)

    return "(no readable content)"
