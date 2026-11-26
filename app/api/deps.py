from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.core.tokens import decode_access_token
from app.models.auth_session import UserSession
from app.models.user import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


async def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: SessionDep,
) -> AuthContext:
    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    try:
        claims = decode_access_token(credentials.credentials)
        user_id = UUID(str(claims["sub"]))
        session_id = UUID(str(claims["sid"]))
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise unauthorized from exc

    auth_session = await db.get(UserSession, session_id)
    now = datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= now
    ):
        raise unauthorized

    user = await db.get(User, user_id)
    if (
        user is None
        or not user.is_active
        or user.email_verified_at is None
    ):
        raise unauthorized

    if auth_session.last_used_at <= now - timedelta(minutes=5):
        auth_session.last_used_at = now
        await db.commit()

    return AuthContext(user=user, session=auth_session)


CurrentAuthDep = Annotated[AuthContext, Depends(get_auth_context)]
