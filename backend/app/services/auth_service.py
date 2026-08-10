"""Orchestrates login, token refresh, and logout.

Owns the transaction boundary for its operations (commits after a successful
write), so callers - the auth API routes - never need to remember to commit
separately. This mirrors why the repositories themselves deliberately don't
commit: exactly one layer should decide when a unit of work is done, and here
that's this service.

Refresh tokens are single-use and tracked in Redis ("refresh_token:{jti}" ->
user_id, TTL'd to match the token's own expiry). This is what makes logout a
real operation instead of a client-side no-op, and what lets a stolen-but-
already-used refresh token be rejected (rotation): every successful refresh
deletes the presented jti and issues a brand new one.
"""
import uuid
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.google_oauth import GoogleOAuthError, exchange_code_for_id_token, verify_google_id_token
from app.auth.jwt import InvalidTokenError, create_access_token, create_refresh_token, decode_refresh_token
from app.config.settings import Settings
from app.database.repositories.user_repository import UserRepository
from app.models.user import User

_REFRESH_TOKEN_KEY_PREFIX = "refresh_token:"


class AuthenticationError(Exception):
    """Any auth failure that should surface as 401 to the client."""


@dataclass
class AuthResult:
    user: User
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, *, db: AsyncSession, users: UserRepository, redis: Redis, settings: Settings) -> None:
        self.db = db
        self.users = users
        self.redis = redis
        self.settings = settings

    async def login_with_google(self, *, code: str, redirect_uri: str) -> AuthResult:
        try:
            google_id_token_str = await exchange_code_for_id_token(code=code, redirect_uri=redirect_uri)
            claims = await verify_google_id_token(google_id_token_str)
        except GoogleOAuthError as exc:
            raise AuthenticationError(str(exc)) from exc

        google_id = claims["sub"]
        email = claims["email"]
        name = claims.get("name") or email
        picture = claims.get("picture")

        user = await self.users.get_by_google_id(google_id)
        if user is None:
            # Google account emails are already verified (checked in
            # verify_google_id_token), but a differently-authenticated user
            # could theoretically already own this email; let the unique
            # constraint be the final word rather than assuming.
            user = await self.users.create(
                google_id=google_id, email=email, name=name, profile_picture=picture
            )
        await self.db.commit()

        access_token, refresh_token = await self._issue_tokens(user.id)
        return AuthResult(user=user, access_token=access_token, refresh_token=refresh_token)

    async def refresh(self, *, refresh_token: str) -> AuthResult:
        try:
            user_id, jti = decode_refresh_token(refresh_token)
        except InvalidTokenError as exc:
            raise AuthenticationError("Invalid refresh token") from exc

        key = f"{_REFRESH_TOKEN_KEY_PREFIX}{jti}"
        stored_user_id = await self.redis.get(key)
        if stored_user_id is None or stored_user_id != str(user_id):
            raise AuthenticationError("Refresh token has been revoked, already used, or expired")

        # Single-use: revoke this token the moment it's redeemed, before
        # issuing its replacement.
        await self.redis.delete(key)

        user = await self.users.get(user_id)
        if user is None:
            raise AuthenticationError("User no longer exists")

        access_token, new_refresh_token = await self._issue_tokens(user.id)
        return AuthResult(user=user, access_token=access_token, refresh_token=new_refresh_token)

    async def logout(self, *, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        try:
            _, jti = decode_refresh_token(refresh_token)
        except InvalidTokenError:
            return  # Already invalid/expired - nothing left to revoke.
        await self.redis.delete(f"{_REFRESH_TOKEN_KEY_PREFIX}{jti}")

    async def _issue_tokens(self, user_id: uuid.UUID) -> tuple[str, str]:
        access_token = create_access_token(user_id)
        refresh_token, jti = create_refresh_token(user_id)
        await self.redis.set(
            f"{_REFRESH_TOKEN_KEY_PREFIX}{jti}",
            str(user_id),
            ex=self.settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )
        return access_token, refresh_token
