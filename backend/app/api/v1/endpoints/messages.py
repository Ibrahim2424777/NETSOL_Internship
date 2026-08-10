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
from app.schemas.message import MessageResponse, SendMessageRequest
from app.services.chat_execution_service import ChatExecutionService
from app.workers.message_persistence import persist_message

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
        yield _sse({"type": "error", "detail": "The assistant failed to respond. Please try again."})
        await _await_quietly(persist_user_task, chat_id, "user")
        return

    # Confirm the user message really made it to Postgres before telling the
    # client we're fully done with this turn.
    await _await_quietly(persist_user_task, chat_id, "user")

    # --- Step 6/7: cache + persist the assistant's full response ---
    assistant_message = MessageResponse(
        id=uuid.uuid4(),
        chat_id=chat_id,
        role=MessageRole.ASSISTANT,
        content=full_response,
        timestamp=datetime.now(timezone.utc),
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
        )
    except Exception:
        logger.exception("Failed to persist assistant message for chat %s", chat_id)
        # The client already has the full reply via the streamed chunks above;
        # a Postgres hiccup here shouldn't throw away a response Gemini
        # already generated successfully. It's logged for follow-up.

    # --- Step 8: signal completion with the authoritative saved message ---
    yield _sse({"type": "done", "message": assistant_payload})


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
