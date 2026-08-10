"""Chat CRUD endpoints. Every route requires auth and every chat-scoped
route (get/rename/delete) resolves and ownership-checks the chat via the
OwnedChat dependency - see app/api/deps.py:get_owned_chat.
"""
from fastapi import APIRouter, status

from app.api.deps import ChatCacheDep, ChatExecution, ChatRepo, CurrentUser, DbSession, OwnedChat
from app.schemas.chat import ChatCreateRequest, ChatRenameRequest, ChatResponse

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    payload: ChatCreateRequest,
    current_user: CurrentUser,
    chats: ChatRepo,
    db: DbSession,
) -> ChatResponse:
    chat = await chats.create(user_id=current_user.id, title=payload.title)
    await db.commit()
    return ChatResponse.model_validate(chat)


@router.get("", response_model=list[ChatResponse])
async def list_chats(current_user: CurrentUser, chats: ChatRepo) -> list[ChatResponse]:
    """Most-recently-active first - what the sidebar renders."""
    chat_list = await chats.list_for_user(current_user.id)
    return [ChatResponse.model_validate(chat) for chat in chat_list]


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(chat: OwnedChat) -> ChatResponse:
    return ChatResponse.model_validate(chat)


@router.patch("/{chat_id}", response_model=ChatResponse)
async def rename_chat(
    payload: ChatRenameRequest,
    chat: OwnedChat,
    chats: ChatRepo,
    db: DbSession,
) -> ChatResponse:
    renamed = await chats.rename(chat, title=payload.title)
    await db.commit()
    return ChatResponse.model_validate(renamed)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat: OwnedChat, chats: ChatRepo, db: DbSession, cache: ChatCacheDep, execution: ChatExecution
) -> None:
    chat_id = chat.id
    # Cascades to the chat's messages at the database level (ON DELETE CASCADE) -
    # see app/models/chat.py / app/models/message.py.
    await chats.delete(chat)
    await db.commit()
    await cache.delete(chat_id)
    # The checkpointer's tables aren't linked to `chats` by a foreign key, so
    # they need their own explicit cleanup - see ChatExecutionService.forget_chat.
    await execution.forget_chat(chat_id)
