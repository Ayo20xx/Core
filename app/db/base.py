from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):

    def __init__(self, model: type[ModelType]):
        self.model = model

    async def add(self, session: AsyncSession, body: ModelType) -> ModelType:
        session.add(body)
        await session.commit()
        await session.refresh(body)
        return body

    async def get(self, session: AsyncSession, id: UUID)-> ModelType| None:
        self.session = session
        return await self.session.get(id)

    async def exists(self, session: AsyncSession, **filters: Any) -> bool:
        Conditions = []
        for key, value in filters.items():
            Column = getattr(self.model, key)
            Conditions.append(Column == value)
        statement = select(self.model).where(*Conditions)
        result = await session.execute(statement)
        return result.first() is not None

    async def update(self, session: AsyncSession, body: ModelType)  -> ModelType:

        session.add(body)
        await session.commit()
        await session.refresh(body)
        return body

    async def delete(self, session: AsyncSession, body: ModelType) -> None:
        session.delete(body)
        await session.commit()