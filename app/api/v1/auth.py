import secrets
from datetime import UTC, datetime

from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, HTTPException

import aiosmtplib
from app.api.deps import SessionDep
from app.core.exceptions import EmailException
from app.core.security import hash_password, verify_password_hash
from app.models.redis import redis_client
from app.repositories.auth_repository import AuthRepository
from app.schemas.user import (
    UsersCreate,
    UsersRead,
    VerificationCodeCreate,
    VerificationEmailRequest,
)
from app.services.auth_service import AuthService
from app.services.mail_service import MailService

router = APIRouter(prefix="/auth", tags=["auth"])

CODE_TTL_SECONDS = 900  # 15 minutes


async def _send_verification_code(email: str) -> None:
    code = f"{secrets.randbelow(1_000_000):06d}"
    await MailService().send_verification_code(email, code)
    await redis_client.setex(
        f"verification:code:{email}",
        CODE_TTL_SECONDS,
        hash_password(code),
    )


@router.post("/register", response_model=UsersRead, status_code=201)
async def register(session: SessionDep, body: UsersCreate) -> UsersRead:
    service = AuthService()
    try:
        user = await service.register(session, body)
    except EmailException as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        await _send_verification_code(user.email)
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

    code_hash = await redis_client.get(key)
    if code_hash is None:
        raise HTTPException(status_code=400, detail="Code expired or not found")

    try:
        verify_password_hash(body.code, code_hash)
    except VerifyMismatchError:
        raise HTTPException(status_code=400, detail="Invalid code")

    await redis_client.delete(key)

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
        await _send_verification_code(email)
    except (ValueError, aiosmtplib.SMTPException, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail="The verification email could not be sent. Check SMTP settings and try again.",
        ) from exc

    return {"detail": "Verification email sent"}
