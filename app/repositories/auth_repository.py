from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class AuthRepository:
    async def add(self, session: AsyncSession, user: User) -> User:

        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    async def get(self, session: AsyncSession, user_id: UUID) -> User | None:
        return await session.get(User, user_id)

    async def exists(self, session: AsyncSession, **filters: Any) -> bool:

        Conditions = []
        for key, value in filters.items():
            Column = getattr(User, key)
            Conditions.append(Column == value)
        statement = select(User).where(*Conditions)
        result = await session.execute(statement)
        return result.first() is not None

    async def get_by_email(self, session: AsyncSession, email: str) -> User | None:

        statement = select(User).where(User.email == email)
        result = await session.execute(statement)
        return result.scalar_one_or_none()