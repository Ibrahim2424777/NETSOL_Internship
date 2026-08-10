from sqlalchemy import select

from app.database.repositories.base import BaseRepository
from app.models.user import User


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_google_id(self, google_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.google_id == google_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        google_id: str,
        email: str,
        name: str,
        profile_picture: str | None = None,
    ) -> User:
        user = User(google_id=google_id, email=email, name=name, profile_picture=profile_picture)
        return await self._save(user)

    async def update_profile(
        self,
        user: User,
        *,
        name: str | None = None,
        profile_picture: str | None = None,
    ) -> User:
        if name is not None:
            user.name = name
        if profile_picture is not None:
            user.profile_picture = profile_picture
        return await self._save(user)
