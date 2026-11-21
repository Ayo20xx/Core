from models import User
from schemas import UsersCreate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import BaseRepository

User_model=BaseRepository(User)

class Auth :
    async def register(self,body:UsersCreate,session:AsyncSession)->User:
       user= User(email= body.email,
             password_hash=hash_password(body.password),
             lastname=body.last_name,
             firstname=body.first_name)

       return await User_model.add(user)


