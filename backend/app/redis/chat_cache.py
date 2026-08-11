"""Active-conversation cache.

Redis here is a fast-retrieval cache only, per the project's storage rule:
PostgreSQL (via MessageRepository) is the source of truth. Every method here
degrades gracefully - if Redis is slow, down, or the key has expired, callers
fall back to Postgres and the conversation is completely unaffected. Nothing
in this file is allowed to be the only copy of a message.
"""
import json
import logging
import uuid
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_TTL_SECONDS = 60 * 60  # active conversations stay cached for 1 hour of inactivity
_MAX_CACHED_MESSAGES = 200


def _key(chat_id: uuid.UUID) -> str:
    return f"chat_messages:{chat_id}"


class ChatCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def add_message(self, chat_id: uuid.UUID, message: dict[str, Any]) -> None:
        key = _key(chat_id)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.rpush(key, json.dumps(message, default=str))
                pipe.ltrim(key, -_MAX_CACHED_MESSAGES, -1)
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
        except Exception:
            # Caching is a performance optimization, not a durability
            # guarantee - PostgreSQL persistence (app/workers/message_persistence.py)
            # is what actually matters, and it does not depend on this call.
            logger.warning("ChatCache.add_message failed for chat %s", chat_id, exc_info=True)

    async def get_messages(self, chat_id: uuid.UUID) -> list[dict[str, Any]] | None:
        """Returns cached messages, or None if there's no usable cache entry
        (missing, expired, or Redis unreachable) - the caller should treat
        None as "go read Postgres", not as "this chat has no messages".

        A hit also refreshes the TTL (sliding expiration), not just writes:
        a conversation someone is actively reading - scrolled back to, but
        not necessarily sending new messages in right now - is exactly what
        "active conversation cache" should mean, so simply viewing it should
        keep it cached, not just adding to it. EXPIRE on a since-evicted key
        is a harmless no-op, so this is always safe to pipeline unconditionally.
        """
        key = _key(chat_id)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.lrange(key, 0, -1)
                pipe.expire(key, _TTL_SECONDS)
                raw_messages, _ = await pipe.execute()
        except Exception:
            logger.warning("ChatCache.get_messages failed for chat %s", chat_id, exc_info=True)
            return None

        if not raw_messages:
            return None
        return [json.loads(item) for item in raw_messages]

    async def replace_messages(self, chat_id: uuid.UUID, messages: list[dict[str, Any]]) -> None:
        """Used to (re)populate the cache from Postgres after a cache miss,
        so the next read is fast."""
        if not messages:
            return
        key = _key(chat_id)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.delete(key)
                pipe.rpush(key, *(json.dumps(m, default=str) for m in messages[-_MAX_CACHED_MESSAGES:]))
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
        except Exception:
            logger.warning("ChatCache.replace_messages failed for chat %s", chat_id, exc_info=True)

    async def remove_message(self, chat_id: uuid.UUID, message_id: uuid.UUID) -> None:
        """Removes one message from the cache by id - used to retract a
        user message that never got a successful assistant reply (see
        messages.py's error path), not the normal append-only path. Unlike
        replace_messages, this correctly clears the key entirely if the
        removed message was the only one cached, rather than leaving a
        stale entry behind."""
        key = _key(chat_id)
        try:
            cached = await self.get_messages(chat_id)
            if cached is None:
                return
            remaining = [m for m in cached if m.get("id") != str(message_id)]
            if len(remaining) == len(cached):
                return  # message wasn't cached - nothing to do
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.delete(key)
                if remaining:
                    pipe.rpush(key, *(json.dumps(m, default=str) for m in remaining))
                    pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
        except Exception:
            logger.warning("ChatCache.remove_message failed for chat %s", chat_id, exc_info=True)

    async def delete(self, chat_id: uuid.UUID) -> None:
        """Called when a chat is deleted, so its cache entry doesn't linger
        for up to an hour after the chat itself is gone."""
        try:
            await self._redis.delete(_key(chat_id))
        except Exception:
            logger.warning("ChatCache.delete failed for chat %s", chat_id, exc_info=True)
