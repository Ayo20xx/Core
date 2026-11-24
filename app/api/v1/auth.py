from fastapi import APIRouter, HTTPException, Depends
import secrets
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.api.deps import SessionDep
from app.core.exceptions import EmailException
from app.core.security import verify_password_hash, hash_password
from app.services.auth_service import AuthService
from app.services.verification_service import VerificationService
from app.schemas.user import UsersCreate, UsersRead, VerificationCodeCreate

router = APIRouter(prefix="/auth", tags=["auth"])

CODE_TTL_SECONDS = 900  # 15 minutes


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/register", response_model=UsersRead, status_code=201)
async def register(session: SessionDep, body: UsersCreate) -> UsersRead:
    service = AuthService()
    try:
        user = await service.register(session, body)
    except EmailException as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # --- Email verification: generate & store code in DB ---
    vservice = VerificationService()
    code = await vservice.generate_and_store_code(session, body.email)

    return UsersRead.model_validate(user)


@router.post("/verify", response_model=UsersRead)
async def verify_code(session: SessionDep, body: VerificationCodeCreate) -> UsersRead:
    email = _normalize_email(body.email)

    vservice = VerificationService()
    code_row = await vservice.verify_code(session, email, body.code)

    if code_row is None:
        raise HTTPException(status_code=400, detail="Code expired, invalid, or not found")

    # Code verified — update user in DB
    from app.repositories.auth_repository import AuthRepository
    repo = AuthRepository()
    user = await repo.get_by_email(session, email=email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.email_verified_at = datetime.now(timezone.utc)  # need import
    user.is_active = True
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return UsersRead.model_validate(user)