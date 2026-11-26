from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Database_url

engine = create_async_engine(
    url= Database_url,
    echo=False,

)

SessionLocal= async_sessionmaker(
    bind= engine,
    class_= AsyncSession,
    expire_on_commit= False 
)

async def get_session():
    async with SessionLocal() as session:
        yield session 