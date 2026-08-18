"""Structured result shapes for the email MCP tools (Phase 17 doc section
8's "structured results" principle, applied to email the same way Phase 16
applied it to weather)."""
from pydantic import BaseModel, Field


class SendEmailResult(BaseModel):
    message_id: str = Field(description="Gmail's ID for the sent message")
    to: str = Field(description="The actual resolved recipient address 'me' was expanded to, if used")
    subject: str
    status: str = Field(description="Always 'sent' - this tool raises rather than returning a failure status")


class EmailSummary(BaseModel):
    message_id: str = Field(description="Pass this to read_email to fetch the full content")
    sender: str
    subject: str
    date: str


class RecentEmailsResult(BaseModel):
    emails: list[EmailSummary]
    count: int = Field(description="Number of emails returned (<= the requested limit)")


class EmailContent(BaseModel):
    message_id: str
    sender: str
    subject: str
    date: str
    body: str = Field(description="Plain-text body; long emails are truncated - see 'truncated' below")
    truncated: bool = Field(description="True if the body was cut short because it exceeded the length limit")
