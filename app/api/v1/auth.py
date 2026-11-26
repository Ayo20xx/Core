import secrets
import hashlib
from datetime import UTC, datetime
from uuid import UUID

import aiosmtplib
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from app.api.deps import CurrentAuthDep, SessionDep
from app.core.config import RedisSettings, auth_setting, setting
from app.core.exceptions import EmailException
from app.core.security import hash_password, verify_password_hash
from app.core.tokens import create_access_token
from app.repositories.auth_repository import AuthRepository
from app.schemas.user import (
    LoginRequest,
    TokenResponse,
    UsersCreate,
    UsersRead,
    VerificationCodeCreate,
    VerificationEmailRequest,
    UserSessionRead,
)
from app.services.auth_service import AuthService
from app.services.mail_service import MailService
from app.services.session_service import (
    InvalidRefreshToken,
    RefreshTokenReuseDetected,
    SessionService,
)

redis_setting = RedisSettings()
redis_client = redis_setting.redis_client()

router = APIRouter(prefix="/auth", tags=["auth"])

CODE_TTL_SECONDS = 900  # 15 minutes
MAX_VERIFICATION_ATTEMPTS = 5
LOGIN_FAILURE_WINDOW_SECONDS = 900
LOGIN_EMAIL_FAILURE_LIMIT = 5
LOGIN_IP_FAILURE_LIMIT = 30
REFRESH_COOKIE_NAME = "core_refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=setting.ENVIRONMENT.lower() in {"production", "prod"},
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=auth_setting.refresh_token_ttl_days * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=setting.ENVIRONMENT.lower() in {"production", "prod"},
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _login_failure_keys(email: str, client_ip: str | None) -> tuple[tuple[str, int], ...]:
    email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
    ip_hash = hashlib.sha256((client_ip or "unknown").encode("utf-8")).hexdigest()
    return (
        (f"auth:login:email:{email_hash}", LOGIN_EMAIL_FAILURE_LIMIT),
        (f"auth:login:ip:{ip_hash}", LOGIN_IP_FAILURE_LIMIT),
    )


async def _check_login_failure_limits(
    keys: tuple[tuple[str, int], ...],
) -> None:
    for key, limit in keys:
        failures = int(await redis_client.get(key) or 0)
        if failures >= limit:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
            )


async def _record_failed_login(keys: tuple[tuple[str, int], ...]) -> None:
    for key, _limit in keys:
        failures = await redis_client.incr(key)
        if failures == 1:
            await redis_client.expire(key, LOGIN_FAILURE_WINDOW_SECONDS)


async def _send_verification_code(email: str) -> None:
    code = f"{secrets.randbelow(1_000_000):06d}"
    key = f"verification:code:{email}"
    await redis_client.setex(
        key,
        CODE_TTL_SECONDS,
        hash_password(code),
    )
    try:
        await MailService().send_verification_code(email, code)
    except (ValueError, aiosmtplib.SMTPException, OSError):
        await redis_client.delete(key)
        raise


@router.post("/register", response_model=UsersRead, status_code=201)
async def register(session: SessionDep, body: UsersCreate) -> UsersRead:
    service = AuthService()
    try:
        user = await service.register(session, body)
    except EmailException as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        await _send_verification_code(user.email)
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Verification is temporarily unavailable. Please request a new code.",
        ) from exc
    except (ValueError, aiosmtplib.SMTPException, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Account created, but the verification email could not be sent. Check SMTP settings and request a new code.",
        ) from exc

    return UsersRead.model_validate(user)


@router.post("/verify", response_model=UsersRead)
async def verify_code(session: SessionDep, body: VerificationCodeCreate) -> UsersRead:
    email = str(body.email).strip().lower()
    key = f"verification:code:{email}"
    attempts_key = f"verification:attempts:{email}"

    try:
        code_hash = await redis_client.get(key)
        if code_hash is None:
            raise HTTPException(status_code=400, detail="Code expired or not found")

        attempts = int(await redis_client.get(attempts_key) or 0)
        if attempts >= MAX_VERIFICATION_ATTEMPTS:
            await redis_client.delete(key)
            raise HTTPException(status_code=429, detail="Too many verification attempts")

        try:
            verify_password_hash(body.code, code_hash)
        except VerifyMismatchError:
            attempts = await redis_client.incr(attempts_key)
            await redis_client.expire(attempts_key, CODE_TTL_SECONDS)
            if attempts >= MAX_VERIFICATION_ATTEMPTS:
                await redis_client.delete(key)
                raise HTTPException(status_code=429, detail="Too many verification attempts")
            raise HTTPException(status_code=400, detail="Invalid code")

        consumed_hash = await redis_client.getdel(key)
        if consumed_hash != code_hash:
            raise HTTPException(status_code=400, detail="Code expired or already used")
        await redis_client.delete(attempts_key)
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Verification is temporarily unavailable. Please try again.",
        ) from exc

    repo = AuthRepository()
    user = await repo.get_by_email(session, email=email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.email_verified_at = datetime.now(UTC)
    user.is_active = True
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return UsersRead.model_validate(user)


@router.post("/verify/resend", status_code=202)
async def resend_verification_code(
    session: SessionDep,
    body: VerificationEmailRequest,
) -> dict[str, str]:
    email = str(body.email).strip().lower()
    user = await AuthRepository().get_by_email(session, email=email)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.email_verified_at is not None:
        raise HTTPException(status_code=409, detail="Email is already verified")

    try:
        await redis_client.delete(
            f"verification:code:{email}",
            f"verification:attempts:{email}",
        )
        await _send_verification_code(email)
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Verification is temporarily unavailable. Please try again.",
        ) from exc
    except (ValueError, aiosmtplib.SMTPException, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail="The verification email could not be sent. Check SMTP settings and try again.",
        ) from exc

    return {"detail": "Verification email sent"}


@router.post("/login", response_model=TokenResponse)
async def login(
    db: SessionDep,
    body: LoginRequest,
    request: Request,
    response: Response,
) -> TokenResponse:
    failure_keys = _login_failure_keys(
        str(body.email),
        request.client.host if request.client else None,
    )
    try:
        await _check_login_failure_limits(failure_keys)
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Login is temporarily unavailable",
        ) from exc

    user = await AuthRepository().get_by_email(db, email=str(body.email))
    if user is None:
        try:
            await _record_failed_login(failure_keys)
        except RedisError as exc:
            raise HTTPException(
                status_code=503,
                detail="Login is temporarily unavailable",
            ) from exc
        raise HTTPException(status_code=401, detail="Invalid email or password")

    try:
        verify_password_hash(body.password, user.password_hash)
    except VerifyMismatchError as exc:
        try:
            await _record_failed_login(failure_keys)
        except RedisError as redis_exc:
            raise HTTPException(
                status_code=503,
                detail="Login is temporarily unavailable",
            ) from redis_exc
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc

    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Verify your email before logging in")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is inactive")

    try:
        await redis_client.delete(*(key for key, _limit in failure_keys))
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Login is temporarily unavailable",
        ) from exc

    user_agent = request.headers.get("user-agent")
    credentials = await SessionService().create_session(
        db,
        user,
        body.device_name.strip() or None if body.device_name else None,
        user_agent[:512] if user_agent else None,
    )
    _set_refresh_cookie(response, credentials.refresh_token)

    return TokenResponse(
        access_token=create_access_token(user.id, credentials.session.id),
        expires_in=auth_setting.access_token_ttl_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    db: SessionDep,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> TokenResponse | JSONResponse:
    if refresh_token is None:
        raise HTTPException(status_code=401, detail="Refresh token is missing")

    try:
        credentials = await SessionService().rotate_refresh_token(db, refresh_token)
    except RefreshTokenReuseDetected:
        error_response = JSONResponse(
            status_code=401,
            content={"detail": "Refresh token reuse detected; this session was revoked"},
        )
        _clear_refresh_cookie(error_response)
        return error_response
    except InvalidRefreshToken:
        error_response = JSONResponse(
            status_code=401,
            content={"detail": "Refresh token is invalid or expired"},
        )
        _clear_refresh_cookie(error_response)
        return error_response

    _set_refresh_cookie(response, credentials.refresh_token)
    return TokenResponse(
        access_token=create_access_token(
            credentials.session.user_id,
            credentials.session.id,
        ),
        expires_in=auth_setting.access_token_ttl_minutes * 60,
    )


@router.post("/logout", status_code=204)
async def logout(
    db: SessionDep,
    current: CurrentAuthDep,
    response: Response,
) -> Response:
    await SessionService().revoke_session(
        db,
        current.session.id,
        current.user.id,
    )
    _clear_refresh_cookie(response)
    response.status_code = 204
    return response


@router.get("/sessions", response_model=list[UserSessionRead])
async def list_user_sessions(
    db: SessionDep,
    current: CurrentAuthDep,
) -> list[UserSessionRead]:
    sessions = await SessionService().list_sessions(db, current.user.id)
    return [
        UserSessionRead.model_validate(item).model_copy(
            update={"is_current": item.id == current.session.id}
        )
        for item in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_user_session(
    session_id: UUID,
    db: SessionDep,
    current: CurrentAuthDep,
    response: Response,
) -> Response:
    revoked = await SessionService().revoke_session(
        db,
        session_id,
        current.user.id,
    )
    if not revoked:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_id == current.session.id:
        _clear_refresh_cookie(response)
    response.status_code = 204
    return response
