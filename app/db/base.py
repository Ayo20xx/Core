from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):

    def __init__(self, model: ModelType):
        self.model = model

    async def add(self, session: AsyncSession, body: ModelType) -> dict:
        self.session = session
        session.add(body)
        await session.commit()
        await session.refresh(body)
        return body

    async def get(self, session: AsyncSession, id: UUID):
        self.session = session
        return self.session.get(id)

    async def exists(self, session: AsyncSession, **filters: Any) -> bool:
        self.session = session
        Conditions = []
        for key, value in filters.items():
            Column = getattr(self.model, key)
            Conditions.append(Column == value)
        statement = select(self.model).where(*Conditions)
        data = await session.execute(statement)
        return data.first is not None

    async def update(self, session: AsyncSession, body: ModelType) -> dict:
        self.session = session
        session.add(body)
        await session.commit()
        await session.refresh(body)
        return body

    async def delete(self, session: AsyncSession, body: ModelType) -> dict:
        self.session = session
        session.delete(body)