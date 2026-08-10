"""FastAPI dependency that resolves the current user from the
`Authorization: Bearer <access_token>` header.

Deliberately does not touch Redis: access tokens are verified as pure,
stateless JWTs (signature + expiry only) so authenticated requests stay fast.
Only the refresh flow (AuthService.refresh), which happens roughly every 15
minutes rather than on every request, pays for a Redis round trip.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import InvalidTokenError, decode_access_token
from app.database.repositories.user_repository import UserRepository
from app.database.session import get_db
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    def unauthorized() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials is None:
        raise unauthorized()

    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise unauthorized() from None

    user = await UserRepository(db).get(user_id)
    if user is None:
        raise unauthorized()
    return user
