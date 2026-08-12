import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.message import MessageRole


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=32_000)
    # Phase 14.6: the frontend's explicit web-search toggle for THIS message
    # only (not a chat-level setting) - forces the chat graph straight to
    # the web_search route, bypassing the normal/RAG classifier entirely.
    # See ChatExecutionService.run_stream's web_search parameter.
    web_search: bool = False

    @field_validator("content")
    @classmethod
    def _reject_whitespace_only(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be empty or whitespace-only")
        return stripped


class MessageSource(BaseModel):
    """One source a grounded reply drew on - either a RAG document chunk
    (source=filename, page=N, url=None) or a web search result (Phase 14.6:
    source=page title, page=None, url=the actual link). Deliberately minimal
    (just enough for "Sources: - filename.pdf (p. 3)" or a clickable link),
    not a full citation with chunk text/score - see Phase 12 doc section 15."""

    source: str
    page: int | None = None
    url: str | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    role: MessageRole
    content: str
    timestamp: datetime
    sources: list[MessageSource] | None = None
