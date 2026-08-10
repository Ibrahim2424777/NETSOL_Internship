"""Centralized dependency-injection utilities.

Route handlers should import what they need from here rather than reaching
into app.database / app.redis / app.config directly — this module is the one
place that wires "how to get a resource" to "what a route asks for", so
routes stay declarative:

    @router.get("/example")
    async def example(db: DbSession, redis_client: RedisClient) -> ...:
        ...

"""
import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import get_current_user
from app.config.settings import Settings, get_settings
from app.database.repositories.chat_repository import ChatRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.user_repository import UserRepository
from app.database.session import get_db
from app.models.chat import Chat
from app.models.user import User
from app.redis.chat_cache import ChatCache
from app.redis.client import get_redis
from app.services.chat_execution_service import ChatExecutionService
from app.services.gemini_service import GeminiService
from app.services.model_service import ModelService

DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


def get_chat_repository(db: DbSession) -> ChatRepository:
    return ChatRepository(db)


def get_message_repository(db: DbSession) -> MessageRepository:
    return MessageRepository(db)


# ChatRepo/MessageRepo aren't consumed by any route yet - ready for the
# chats/messages API phase.
UserRepo = Annotated[UserRepository, Depends(get_user_repository)]
ChatRepo = Annotated[ChatRepository, Depends(get_chat_repository)]
MessageRepo = Annotated[MessageRepository, Depends(get_message_repository)]


@lru_cache
def get_model_service() -> ModelService:
    """The one place that decides Gemini is today's model provider. Everything
    downstream (the graph, the node, ChatExecutionService) depends only on
    the ModelService interface, so swapping providers later means changing
    only this function.
    """
    settings = get_settings()
    return GeminiService(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)


def get_chat_execution_service(request: Request) -> ChatExecutionService:
    """Built once in app/main.py's lifespan (it needs an async-initialized
    checkpointer connection pool, which a plain @lru_cache no-arg factory
    can't do) and stored on app.state - this just reads it back, so it's
    still effectively a singleton per process, not created per-request."""
    return request.app.state.chat_execution_service


ModelServiceDep = Annotated[ModelService, Depends(get_model_service)]
ChatExecution = Annotated[ChatExecutionService, Depends(get_chat_execution_service)]


def get_chat_cache(redis_client: RedisClient) -> ChatCache:
    return ChatCache(redis_client)


ChatCacheDep = Annotated[ChatCache, Depends(get_chat_cache)]


async def get_owned_chat(chat_id: uuid.UUID, current_user: CurrentUser, chats: ChatRepo) -> Chat:
    """Resolves chat_id from the path and verifies the current user owns it.

    Any route that declares `chat: OwnedChat` gets this for free - FastAPI
    matches the `chat_id` parameter below to that route's own path parameter.
    404 (not 403) on a chat that exists but belongs to someone else: the
    response must not reveal that the ID is valid for a different account.
    """
    chat = await chats.get(chat_id)
    if chat is None or chat.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


OwnedChat = Annotated[Chat, Depends(get_owned_chat)]
