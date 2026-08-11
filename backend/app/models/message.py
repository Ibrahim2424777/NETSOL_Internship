import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.chat import Chat


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Every read of a conversation is "messages for this chat, in order" -
        # this one composite index serves both the chat_id filter and the
        # timestamp ordering.
        Index("ix_messages_chat_id_timestamp", "chat_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    # native_enum=False stores this as VARCHAR + a CHECK constraint rather
    # than a Postgres ENUM type, since future nodes (tool calling, multi-agent)
    # will likely need new roles - adding one is then a plain migration
    # instead of the more delicate ALTER TYPE ... ADD VALUE dance.
    # values_callable: without it, SQLAlchemy stores the member *name*
    # ("USER") instead of "user", even though MessageRole is a str enum.
    # create_constraint: SQLAlchemy 2.0 defaults this to False, i.e. no actual
    # CHECK constraint - the column would silently accept any string.
    role: Mapped[MessageRole] = mapped_column(
        SAEnum(
            MessageRole,
            native_enum=False,
            validate_strings=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            create_constraint=True,
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL for every message except a RAG-grounded assistant reply (Phase
    # 12) - a list of {"source": ..., "page": ...} objects identifying which
    # ingested document chunks the answer was generated from. Retained here
    # (not just sent over SSE) so it survives a page refresh - see
    # app/api/v1/endpoints/messages.py.
    sources: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chat: Mapped["Chat"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"Message(id={self.id!r}, chat_id={self.chat_id!r}, role={self.role!r})"
