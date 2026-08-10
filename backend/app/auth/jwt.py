"""Encoding and decoding of our own JWTs (access + refresh).

Deliberately has no knowledge of Google, Redis, or the database - it only
knows how to mint and verify tokens. app/services/auth_service.py is what
ties this together with user lookup and refresh-token revocation.

Access and refresh tokens are signed with two DIFFERENT secrets
(JWT_SECRET / JWT_REFRESH_SECRET), so a leaked access-token secret alone
can't be used to forge a refresh token, or vice versa. The "type" claim is a
second, belt-and-suspenders check against a token minted for one purpose
being accepted for the other.
"""
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

import jwt

from app.config.settings import get_settings

ALGORITHM = "HS256"


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": TokenType.ACCESS.value,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str]:
    """Returns (token, jti). The caller (AuthService) stores jti in Redis as
    the allowlist entry for this token, enabling revocation and rotation."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "type": TokenType.REFRESH.value,
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": jti,
    }
    token = jwt.encode(payload, settings.JWT_REFRESH_SECRET, algorithm=ALGORITHM)
    return token, jti


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != TokenType.ACCESS.value:
        raise InvalidTokenError("Token is not an access token")

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("Token subject is not a valid user id") from exc


def decode_refresh_token(token: str) -> tuple[uuid.UUID, str]:
    """Returns (user_id, jti). Only verifies the JWT itself - the caller is
    responsible for checking jti against the Redis allowlist."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_REFRESH_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != TokenType.REFRESH.value:
        raise InvalidTokenError("Token is not a refresh token")

    jti = payload.get("jti")
    if not jti:
        raise InvalidTokenError("Refresh token is missing jti")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("Token subject is not a valid user id") from exc

    return user_id, jti
