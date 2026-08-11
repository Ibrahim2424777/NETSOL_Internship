"""Send Message (streamed) and Get Messages.

See the Phase 5 message-flow write-up for the full step-by-step explanation.
In short: the user's message is cached in Redis and durably persisted to
Postgres concurrently with the Gemini call - not blocking it - the AI's
reply is streamed to the client as Server-Sent Events as it's generated, and
once complete, the reply is cached and durably persisted the same way before
the stream closes.
"""
import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from app.api.deps import ChatCacheDep, ChatExecution, MessageRepo, OwnedChat
from app.models.message import MessageRole
from app.redis.chat_cache import ChatCache
from app.schemas.message import MessageResponse, MessageSource, SendMessageRequest
from app.services.chat_execution_service import ChatExecutionService
from app.workers.message_persistence import persist_message, remove_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chats/{chat_id}/messages", tags=["messages"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _stream_message(
    *,
    chat_id: uuid.UUID,
    user_content: str,
    execution: ChatExecutionService,
    cache: ChatCache,
) -> AsyncIterator[str]:
    # --- Step 1/2: receive the message, cache it immediately ---
    # id/timestamp are generated here (not left to Postgres defaults) so the
    # Redis copy and the eventual Postgres row are unambiguously the same
    # message, and so we have a real id to hand back to the client right away.
    user_message = MessageResponse(
        id=uuid.uuid4(),
        chat_id=chat_id,
        role=MessageRole.USER,
        content=user_content,
        timestamp=datetime.now(timezone.utc),
    )
    user_payload = user_message.model_dump(mode="json")
    await cache.add_message(chat_id, user_payload)

    # --- Step 3: persist to Postgres concurrently - NOT awaited here, so it
    # runs alongside the Gemini call instead of delaying it. ---
    persist_user_task = asyncio.create_task(
        persist_message(
            id=user_message.id,
            chat_id=chat_id,
            role=MessageRole.USER,
            content=user_message.content,
            timestamp=user_message.timestamp,
        )
    )

    yield _sse({"type": "user_message", "message": user_payload})

    # --- Step 4/5: run the LangGraph workflow, streaming Gemini's reply ---
    # chat_id doubles as the LangGraph thread_id: only this turn's message is
    # passed in, the checkpointer supplies the rest of the conversation (see
    # app/services/chat_execution_service.py). An empty response is treated
    # as a failure inside model_node itself (raises rather than returning),
    # so it surfaces here the same way any other model-layer error does.
    full_response = ""
    try:
        async for chunk in execution.run_stream(chat_id, user_content):
            full_response += chunk
            yield _sse({"type": "chunk", "content": chunk})
    except Exception:
        logger.exception("Streaming failed for chat %s", chat_id)
        # Un-send the user's message: without this, a failed turn leaves the
        # question sitting in the chat, and retrying looks like the same
        # thing was sent twice once the retry succeeds.
        await _await_quietly(persist_user_task, chat_id, "user")
        await _retract_user_message(cache, chat_id, user_message.id)
        yield _sse(
            {
                "type": "error",
                "detail": "The assistant failed to respond. Please try again.",
                "removed_message_id": str(user_message.id),
            }
        )
        return

    # Confirm the user message really made it to Postgres before telling the
    # client we're fully done with this turn.
    await _await_quietly(persist_user_task, chat_id, "user")

    # --- Step 6/7: cache + persist the assistant's full response ---
    sources = await _retrieved_sources(execution, chat_id)
    assistant_message = MessageResponse(
        id=uuid.uuid4(),
        chat_id=chat_id,
        role=MessageRole.ASSISTANT,
        content=full_response,
        timestamp=datetime.now(timezone.utc),
        sources=sources,
    )
    assistant_payload = assistant_message.model_dump(mode="json")
    await cache.add_message(chat_id, assistant_payload)

    try:
        await persist_message(
            id=assistant_message.id,
            chat_id=chat_id,
            role=MessageRole.ASSISTANT,
            content=assistant_message.content,
            timestamp=assistant_message.timestamp,
            sources=assistant_payload["sources"],
        )
    except Exception:
        logger.exception("Failed to persist assistant message for chat %s", chat_id)
        # The client already has the full reply via the streamed chunks above;
        # a Postgres hiccup here shouldn't throw away a response Gemini
        # already generated successfully. It's logged for follow-up.

    # --- Step 8: signal completion with the authoritative saved message ---
    yield _sse({"type": "done", "message": assistant_payload})


async def _retrieved_sources(
    execution: ChatExecutionService, chat_id: uuid.UUID
) -> list[MessageSource] | None:
    """Reads back this turn's retrieved chunks (Phase 12) and collapses them
    to one entry per distinct (source, page) - several chunks commonly come
    from the same page, and the UI only ever shows a flat "Sources used"
    list, not one line per chunk. None (not []) when nothing was retrieved,
    so plain conversational replies don't get an empty sources array."""
    try:
        chunks = await execution.get_retrieved_sources(chat_id)
    except Exception:
        logger.exception("Failed to read back retrieved sources for chat %s", chat_id)
        return None

    if not chunks:
        return None

    seen: set[tuple[str, int | None]] = set()
    sources: list[MessageSource] = []
    for chunk in chunks:
        key = (chunk["source"], chunk["page"])
        if key not in seen:
            seen.add(key)
            sources.append(MessageSource(source=chunk["source"], page=chunk["page"]))
    return sources


async def _retract_user_message(cache: ChatCache, chat_id: uuid.UUID, message_id: uuid.UUID) -> None:
    """Un-sends the user's message after a failed assistant reply: removes
    it from the Redis cache and, if persist_user_task made it that far, the
    Postgres row too. Never raises - the client-facing error event matters
    more than this cleanup succeeding; a leftover row/cache entry here is
    logged, not fatal (mirrors how a failed assistant-message persist is
    already treated a few lines up)."""
    await cache.remove_message(chat_id, message_id)
    try:
        await remove_message(id=message_id, chat_id=chat_id)
    except Exception:
        logger.exception(
            "Failed to remove user message %s for chat %s after a failed assistant reply",
            message_id,
            chat_id,
        )


async def _await_quietly(task: asyncio.Task, chat_id: uuid.UUID, label: str) -> None:
    try:
        await task
    except Exception:
        logger.exception("Failed to persist %s message for chat %s", label, chat_id)


@router.post("")
async def send_message(
    payload: SendMessageRequest,
    chat: OwnedChat,
    execution: ChatExecution,
    cache: ChatCacheDep,
) -> StreamingResponse:
    return StreamingResponse(
        _stream_message(chat_id=chat.id, user_content=payload.content, execution=execution, cache=cache),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Disable response buffering if this ever ends up behind Nginx -
            # otherwise Nginx would hold the whole stream until it closes.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("", response_model=list[MessageResponse])
async def get_messages(
    chat: OwnedChat,
    messages: MessageRepo,
    cache: ChatCacheDep,
) -> list[MessageResponse]:
    cached = await cache.get_messages(chat.id)
    if cached is not None:
        return [MessageResponse.model_validate(m) for m in cached]

    db_messages = await messages.list_for_chat(chat.id)
    response = [MessageResponse.model_validate(m) for m in db_messages]

    await cache.replace_messages(chat.id, [m.model_dump(mode="json") for m in response])

    return response
