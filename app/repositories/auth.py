from app.models.user import User
from app.schemas.user import UsersCreate

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import BaseRepository

auth_repo = BaseRepository(User)


class Auth:
    async def register(self, body: UsersCreate, session: AsyncSession) -> User:
        user = User(
            email=body.email,
            password_hash=hash_password(body.password),
            first_name=body.first_name,
            last_name=body.last_name,
            email_verified_at=None,
            is_active=True,
        )

        return await auth_repo.add(session, user)