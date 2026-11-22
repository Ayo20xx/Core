from models import User
from schemas import UsersCreate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import BaseRepository

Auth_repo=BaseRepository(User,AsyncSession)

class EmailException(Exception):
    pass

class Auth:
    async def register(self,body:UsersCreate)->User:
       if await Auth_repo.exists(body.email):
           raise EmailException("This email already exists")
       user= User(email= body.email,
             password_hash=hash_password(body.password),
             last_name=body.last_name,
             first_name=body.first_name,
             email_verified_at = None,
             is_active=True   )

       return await Auth_repo.add(user)


