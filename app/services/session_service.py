from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import auth_setting
from app.models.auth_session import RefreshToken, UserSession
from app.models.user import User


class InvalidRefreshToken(Exception):
    pass


class RefreshTokenReuseDetected(InvalidRefreshToken):
    pass


@dataclass(frozen=True)
class SessionCredentials:
    session: UserSession
    refresh_token: str


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionService:
    async def create_session(
        self,
        db: AsyncSession,
        user: User,
        device_name: str | None,
        user_agent: str | None,
    ) -> SessionCredentials:
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=auth_setting.refresh_token_ttl_days)
        session_row = UserSession(
            id=uuid4(),
            user_id=user.id,
            device_name=device_name,
            user_agent=user_agent,
            created_at=now,
            last_used_at=now,
            expires_at=expires_at,
        )
        raw_token = secrets.token_urlsafe(32)
        token_row = RefreshToken(
            id=uuid4(),
            session_id=session_row.id,
            token_hash=hash_refresh_token(raw_token),
            created_at=now,
            expires_at=expires_at,
        )
        db.add(session_row)
        await db.flush()
        db.add(token_row)
        await db.commit()
        return SessionCredentials(session=session_row, refresh_token=raw_token)

    async def rotate_refresh_token(
        self,
        db: AsyncSession,
        raw_token: str,
    ) -> SessionCredentials:
        now = datetime.now(UTC)
        result = await db.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
            .with_for_update()
        )
        token_row = result.scalar_one_or_none()
        if token_row is None:
            await db.rollback()
            raise InvalidRefreshToken

        result = await db.execute(
            select(UserSession)
            .where(UserSession.id == token_row.session_id)
            .with_for_update()
        )
        session_row = result.scalar_one_or_none()
        if session_row is None:
            await db.rollback()
            raise InvalidRefreshToken

        if token_row.used_at is not None:
            await self._revoke(db, session_row, now)
            await db.commit()
            raise RefreshTokenReuseDetected

        if (
            token_row.revoked_at is not None
            or session_row.revoked_at is not None
            or token_row.expires_at <= now
            or session_row.expires_at <= now
        ):
            await db.rollback()
            raise InvalidRefreshToken

        user = await db.get(User, session_row.user_id)
        if user is None or not user.is_active or user.email_verified_at is None:
            await self._revoke(db, session_row, now)
            await db.commit()
            raise InvalidRefreshToken

        new_raw_token = secrets.token_urlsafe(32)
        new_token_id = uuid4()
        new_token_row = RefreshToken(
            id=new_token_id,
            session_id=session_row.id,
            token_hash=hash_refresh_token(new_raw_token),
            created_at=now,
            expires_at=session_row.expires_at,
        )
        db.add(new_token_row)
        await db.flush()
        token_row.used_at = now
        token_row.replaced_by_id = new_token_id
        session_row.last_used_at = now
        await db.commit()

        return SessionCredentials(session=session_row, refresh_token=new_raw_token)

    async def list_sessions(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> list[UserSession]:
        result = await db.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .order_by(UserSession.last_used_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_session(
        self,
        db: AsyncSession,
        session_id: UUID,
        user_id: UUID,
    ) -> bool:
        result = await db.execute(
            select(UserSession)
            .where(
                UserSession.id == session_id,
                UserSession.user_id == user_id,
            )
            .with_for_update()
        )
        session_row = result.scalar_one_or_none()
        if session_row is None:
            await db.rollback()
            return False
        await self._revoke(db, session_row, datetime.now(UTC))
        await db.commit()
        return True

    @staticmethod
    async def _revoke(
        db: AsyncSession,
        session_row: UserSession,
        now: datetime,
    ) -> None:
        session_row.revoked_at = now
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id == session_row.id)
            .values(revoked_at=now)
        )
