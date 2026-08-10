"""Background persistence of chat messages to PostgreSQL - the durable,
authoritative copy (see the Message Flow explanation for how this fits
together with the Redis cache).

Runs with its OWN database session rather than reusing the request's. This
matters because these calls execute concurrently with (via asyncio.create_task)
or immediately after the streaming response that triggered them, and
SQLAlchemy's AsyncSession is not safe to use from more than one place at a
time - reusing a request-scoped session here would risk corrupting it.
"""
import logging
import uuid
from datetime import datetime

from app.database.repositories.chat_repository import ChatRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.session import AsyncSessionLocal
from app.models.message import Message, MessageRole

logger = logging.getLogger(__name__)


async def persist_message(
    *,
    id: uuid.UUID,
    chat_id: uuid.UUID,
    role: MessageRole,
    content: str,
    timestamp: datetime,
) -> Message:
    """Writes one message (with a caller-supplied id/timestamp, so this row
    matches the one already handed to the client and cached in Redis) and
    bumps the parent chat's updated_at, as a single committed unit of work in
    its own session."""
    async with AsyncSessionLocal() as session:
        messages = MessageRepository(session)
        chats = ChatRepository(session)

        message = await messages.create(
            id=id, chat_id=chat_id, role=role, content=content, timestamp=timestamp
        )

        chat = await chats.get(chat_id)
        if chat is not None:
            await chats.touch(chat)
        else:
            logger.warning("persist_message: chat %s vanished before touch", chat_id)

        await session.commit()
        logger.debug("Persisted %s message %s for chat %s", role.value, message.id, chat_id)
        return message
