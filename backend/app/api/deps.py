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
from app.mcp.client import MCPClientService
from app.redis.chat_cache import ChatCache
from app.redis.client import get_redis
from app.services.chat_execution_service import ChatExecutionService
from app.services.fallback_model_service import FallbackModelService
from app.services.gemini_service import GeminiService
from app.services.groq_service import GroqService
from app.services.model_service import ModelService
from app.services.tavily_service import TavilySearchService

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
def _get_gemini_service() -> GeminiService:
    settings = get_settings()
    return GeminiService(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)


@lru_cache
def get_model_service() -> ModelService:
    """The one place that decides which model provider(s) handle
    routing/normal/RAG/web-search-generation (Phase 14.5; web search joined
    this shared pairing in Phase 18 once Tavily took over retrieval and
    Groq's compound-mini was retired - there is no separate provider
    pairing for any route anymore). Everything downstream (the graph, the
    router/model/web-search-answer nodes, ChatExecutionService) depends only
    on the ModelService interface - it has no idea whether it's holding a
    bare GeminiService, a bare GroqService, or a FallbackModelService
    wrapping both, so adding/removing/reordering providers only ever means
    changing this function.

    LLM_PROVIDER=groq is a development-only escape hatch (Phase 14.5 doc
    section 15) for testing Groq directly without wrapping it in fallback
    logic it doesn't need when it's already the only provider in play.
    """
    settings = get_settings()
    gemini = _get_gemini_service()

    if settings.LLM_PROVIDER == "groq":
        if not settings.GROQ_API_KEY:
            raise RuntimeError("LLM_PROVIDER=groq requires GROQ_API_KEY to be set")
        return GroqService(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)

    # Default: Gemini primary. Only wrap it in fallback logic if a fallback
    # is actually configured and usable - otherwise this behaves exactly as
    # it did before Groq existed (a bare GeminiService, no wrapper).
    if settings.LLM_FALLBACK_PROVIDER == "groq" and settings.GROQ_API_KEY:
        groq_fallback = GroqService(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
        return FallbackModelService(
            gemini, groq_fallback, primary_name="gemini", fallback_name="groq"
        )

    return gemini


@lru_cache
def get_tavily_service() -> TavilySearchService:
    """The web_search route's retrieval layer (Phase 18, replacing Groq
    compound-mini). Only web_search_node.py uses this - routing/normal/RAG
    never do. Without a TAVILY_API_KEY, TavilySearchService.configured is
    False and web_search_node.py degrades to an ungrounded answer rather
    than crashing (see that module and app/services/tavily_service.py)."""
    settings = get_settings()
    return TavilySearchService(
        api_key=settings.TAVILY_API_KEY,
        max_results=settings.WEB_SEARCH_MAX_RESULTS,
        timeout_seconds=settings.WEB_SEARCH_TIMEOUT_SECONDS,
    )


@lru_cache
def get_mcp_client() -> MCPClientService:
    """The one place that knows the standalone MCP server's URL (Phase 17
    doc section 22 - never hardcoded elsewhere). Only agent_node.py (via
    ChatExecutionService/build_chat_graph) actually calls this client -
    nothing else in the backend is allowed to know MCP exists, per the
    doc's "MCP server is the boundary around weather/email" requirement."""
    settings = get_settings()
    return MCPClientService(settings.MCP_SERVER_URL, timeout_seconds=settings.MCP_REQUEST_TIMEOUT_SECONDS)


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
