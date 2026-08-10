"""Generic repository providing the operations shared by every concrete
repository. Concrete repositories (UserRepository, ChatRepository,
MessageRepository) subclass this and add typed, domain-specific methods
instead of relying on generic **kwargs, so callers get real type checking.

Repositories stage changes (add/flush) but never call commit() - the caller
owns the transaction boundary. This matches app.database.session.get_db(),
which also never auto-commits: a single request may need several repository
calls to succeed or fail together as one transaction.
"""
import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: uuid.UUID) -> ModelType | None:
        return await self.session.get(self.model, id)

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[ModelType]:
        result = await self.session.execute(select(self.model).limit(limit).offset(offset))
        return list(result.scalars().all())

    async def delete(self, instance: ModelType) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def _save(self, instance: ModelType) -> ModelType:
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance
