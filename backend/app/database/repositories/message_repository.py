import uuid
from datetime import datetime

from sqlalchemy import select

from app.database.repositories.base import BaseRepository
from app.models.message import Message, MessageRole


class MessageRepository(BaseRepository[Message]):
    model = Message

    async def create(
        self,
        *,
        chat_id: uuid.UUID,
        role: MessageRole,
        content: str,
        id: uuid.UUID | None = None,
        timestamp: datetime | None = None,
    ) -> Message:
        """id/timestamp are normally left to their model defaults. The
        streaming send-message flow passes them explicitly so the message
        cached in Redis and the row persisted to Postgres are provably the
        same message, not two independently-generated near-duplicates."""
        message = Message(chat_id=chat_id, role=role, content=content)
        if id is not None:
            message.id = id
        if timestamp is not None:
            message.timestamp = timestamp
        return await self._save(message)

    async def list_for_chat(
        self, chat_id: uuid.UUID, *, limit: int = 200, offset: int = 0
    ) -> list[Message]:
        """Chronological order - how a conversation is read."""
        result = await self.session.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.timestamp.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
