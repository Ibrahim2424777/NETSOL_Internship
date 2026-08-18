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
    # Shared by get_model_service() and get_web_search_model_service() -
    # both want a Gemini instance (as primary for one, fallback for the
    # other), and there's no reason to hold two separate genai.Client
    # objects/connections for the same API key.
    settings = get_settings()
    return GeminiService(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)


@lru_cache
def get_model_service() -> ModelService:
    """The one place that decides which model provider(s) handle
    routing/normal/RAG (Phase 14.5). Everything downstream (the graph, the
    router and model nodes, ChatExecutionService) depends only on the
    ModelService interface - it has no idea whether it's holding a bare
    GeminiService, a bare GroqService, or a FallbackModelService wrapping
    both, so adding/removing/reordering providers only ever means changing
    this function. See get_web_search_model_service() below for the
    web_search route's separate (reversed) provider pairing.

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
def get_web_search_model_service() -> ModelService:
    """The web_search route's own provider pairing (Phase 14.6) - Groq's
    compound-mini PRIMARY (it does its own live web search while
    generating), Gemini FALLBACK. This is the reverse of get_model_service()
    above: for this one route, the search capability is the entire reason
    to call Groq, so it isn't relegated to fallback duty here. Only the
    web_search node (app/langgraph/nodes/web_search_node.py) uses this -
    routing/normal/RAG never do.

    Without a GROQ_API_KEY, this degrades to bare Gemini - same "the app
    still starts, just without the extra capability" pattern as
    get_model_service() - so a turn explicitly routed to web_search still
    gets an answer (from Gemini's own knowledge), just without live search,
    rather than crashing.
    """
    settings = get_settings()
    gemini = _get_gemini_service()

    if not settings.GROQ_API_KEY:
        return gemini

    compound = GroqService(api_key=settings.GROQ_API_KEY, model=settings.GROQ_COMPOUND_MODEL)
    return FallbackModelService(
        compound, gemini, primary_name="groq-compound", fallback_name="gemini"
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
