from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Database_url

create_engine = create_async_engine(
    url= Database_url,
    echo= True 

)

async def session():
    pass