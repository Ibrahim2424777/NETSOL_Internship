"""Authentication endpoints: Google OAuth login, logout, token refresh,
current user.

Access tokens go in the JSON response body (the frontend attaches them as an
Authorization: Bearer header on subsequent requests). Refresh tokens go ONLY
in a secure, HTTP-only cookie scoped to this router's path - never exposed to
JS, so an XSS bug can't read it, and never accepted from a request body.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import CurrentUser, DbSession, RedisClient, SettingsDep
from app.config.settings import Settings
from app.database.repositories.user_repository import UserRepository
from app.schemas.auth import GoogleLoginRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthenticationError, AuthResult, AuthService
from app.utils.rate_limit import rate_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Login attempts are rarer and more valuable to an attacker (credential
# stuffing) than refreshes, which fire routinely as normal app behavior
# (proactive refresh on load, reactive refresh-on-401) - hence the gap
# between the two limits.
_login_rate_limit = rate_limiter(limit=10, window_seconds=60, bucket="auth-google")
_refresh_rate_limit = rate_limiter(limit=20, window_seconds=60, bucket="auth-refresh")

REFRESH_COOKIE_NAME = "refresh_token"
# Covers /auth/refresh and /auth/logout, the only endpoints that need to read
# this cookie - it is never sent to unrelated routes.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _build_service(db: DbSession, redis_client: RedisClient, settings: Settings) -> AuthService:
    return AuthService(db=db, users=UserRepository(db), redis=redis_client, settings=settings)


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        # Lax: the browser withholds this cookie on cross-site POSTs (e.g. a
        # forged form on another domain targeting /auth/refresh), which is
        # what would otherwise make this endpoint CSRF-able. Still sent on
        # same-site requests, including cross-port localhost dev.
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _token_response(result: AuthResult, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(result.user),
    )


@router.post("/google", response_model=TokenResponse, dependencies=[Depends(_login_rate_limit)])
async def login_with_google(
    payload: GoogleLoginRequest,
    response: Response,
    db: DbSession,
    redis_client: RedisClient,
    settings: SettingsDep,
) -> TokenResponse:
    """Verifies the authorization code with Google, creating the user on
    first login, then issues our own access + refresh tokens."""
    service = _build_service(db, redis_client, settings)
    try:
        result = await service.login_with_google(code=payload.code, redirect_uri=payload.redirect_uri)
    except AuthenticationError as exc:
        logger.warning("Google login failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Google authentication failed"
        ) from exc

    _set_refresh_cookie(response, result.refresh_token, settings)
    return _token_response(result, settings)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(_refresh_rate_limit)])
async def refresh_token(
    request: Request,
    response: Response,
    db: DbSession,
    redis_client: RedisClient,
    settings: SettingsDep,
) -> TokenResponse:
    """Exchanges the refresh cookie for a new access token, rotating the
    refresh token (the old one becomes invalid, whether or not it's reused)."""
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token provided")

    service = _build_service(db, redis_client, settings)
    try:
        result = await service.refresh(refresh_token=token)
    except AuthenticationError as exc:
        response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        logger.info("Refresh rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired, please log in again"
        ) from exc

    _set_refresh_cookie(response, result.refresh_token, settings)
    return _token_response(result, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
    redis_client: RedisClient,
    settings: SettingsDep,
) -> None:
    """Revokes the refresh token server-side (not just a client-side
    discard) and clears the cookie."""
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    service = _build_service(db, redis_client, settings)
    await service.logout(refresh_token=token)
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
