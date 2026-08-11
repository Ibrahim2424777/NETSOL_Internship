import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.message import MessageRole


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=32_000)

    @field_validator("content")
    @classmethod
    def _reject_whitespace_only(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be empty or whitespace-only")
        return stripped


class MessageSource(BaseModel):
    """One document a RAG-grounded reply drew on - deliberately minimal
    (just enough for "Sources: - filename.pdf (p. 3)"), not a full citation
    with chunk text/score - see Phase 12 doc section 15."""

    source: str
    page: int | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    role: MessageRole
    content: str
    timestamp: datetime
    sources: list[MessageSource] | None = None
