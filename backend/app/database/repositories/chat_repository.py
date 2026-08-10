import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.repositories.base import BaseRepository
from app.models.chat import Chat


class ChatRepository(BaseRepository[Chat]):
    model = Chat

    async def create(self, *, user_id: uuid.UUID, title: str = "New Chat") -> Chat:
        chat = Chat(user_id=user_id, title=title)
        return await self._save(chat)

    async def get_with_messages(self, chat_id: uuid.UUID) -> Chat | None:
        """Fetch a chat with its messages eagerly loaded in one round trip,
        instead of triggering a lazy-load query per access."""
        result = await self.session.execute(
            select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.messages))
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Chat]:
        """Most-recently-active chats first, for the sidebar."""
        result = await self.session.execute(
            select(Chat)
            .where(Chat.user_id == user_id)
            .order_by(Chat.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def rename(self, chat: Chat, *, title: str) -> Chat:
        chat.title = title
        return await self._save(chat)

    async def touch(self, chat: Chat) -> Chat:
        """Bump updated_at, e.g. after a new message is added, so the chat
        resurfaces at the top of the user's sidebar ordering."""
        chat.updated_at = datetime.now(timezone.utc)
        return await self._save(chat)
