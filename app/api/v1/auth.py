import secrets
from datetime import UTC, datetime

import aiosmtplib
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, HTTPException
from redis.exceptions import RedisError

from app.api.deps import SessionDep
from app.core.config import RedisSettings
from app.core.exceptions import EmailException
from app.core.security import hash_password, verify_password_hash
from app.repositories.auth_repository import AuthRepository
from app.schemas.user import (
    UsersCreate,
    UsersRead,
    VerificationCodeCreate,
    VerificationEmailRequest,
)
from app.services.auth_service import AuthService
from app.services.mail_service import MailService

redis_setting = RedisSettings()
redis_client = redis_setting.redis_client()

router = APIRouter(prefix="/auth", tags=["auth"])

CODE_TTL_SECONDS = 900  # 15 minutes
MAX_VERIFICATION_ATTEMPTS = 5


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
