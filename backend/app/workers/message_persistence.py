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
    sources: list[dict] | None = None,
) -> Message:
    """Writes one message (with a caller-supplied id/timestamp, so this row
    matches the one already handed to the client and cached in Redis) and
    bumps the parent chat's updated_at, as a single committed unit of work in
    its own session."""
    async with AsyncSessionLocal() as session:
        messages = MessageRepository(session)
        chats = ChatRepository(session)

        message = await messages.create(
            id=id, chat_id=chat_id, role=role, content=content, timestamp=timestamp, sources=sources
        )

        chat = await chats.get(chat_id)
        if chat is not None:
            await chats.touch(chat)
        else:
            logger.warning("persist_message: chat %s vanished before touch", chat_id)

        await session.commit()
        logger.debug("Persisted %s message %s for chat %s", role.value, message.id, chat_id)
        return message


async def remove_message(*, id: uuid.UUID, chat_id: uuid.UUID) -> None:
    """Deletes a message row - used to retract a user message that never
    got a successful assistant reply (see messages.py's error path), so a
    failed send doesn't leave a half-finished turn sitting in Postgres that
    would look like a duplicate once the user successfully retries.

    A no-op (with a warning) if the row doesn't exist - this runs after
    persist_message's own task has already been awaited, but that task may
    itself have failed before ever inserting the row, in which case there's
    nothing here to delete."""
    async with AsyncSessionLocal() as session:
        messages = MessageRepository(session)
        message = await messages.get(id)
        if message is None or message.chat_id != chat_id:
            logger.warning("remove_message: message %s not found for chat %s", id, chat_id)
            return

        await messages.delete(message)
        await session.commit()
        logger.debug("Removed message %s for chat %s (no assistant reply)", id, chat_id)
