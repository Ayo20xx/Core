from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository (Generic[ModelType]):

    def __init__(self,model:ModelType,session:AsyncSession ):
        self.model = model
        self.session = session

    async def get (self, id:UUID):
        return self.session.get(id)

    async def exists(self,**filters:Any)->bool:
        Conditions = []
        for key,value in filters.items() :
            Column = getattr(self.model,key)
            Conditions.append(Column==value)
        statement=select(self.model).where(*Conditions)
        data=await self.session.execute(statement)
        return data.first is not None

    
    async def add(self,body:ModelType)->dict :
       self.session.add(body)
       await self.session.commit()
       await self.session.refresh(body)
       return body 
    
    async def update(self,body:ModelType)->dict:
       self.session.add(body)
       await self.session.commit()
       await self.session.refresh(body)
       return body 

    async def delete(self,body:ModelType)->dict:
        self.session.delete(body)

        


