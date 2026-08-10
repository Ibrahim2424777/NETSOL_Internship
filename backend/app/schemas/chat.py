import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatCreateRequest(BaseModel):
    title: str = Field(default="New Chat", max_length=255)


class ChatRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
