from models import User
from schemas import UsersCreate
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import hash_password

class auth :
    def register(body:UsersCreate,session:AsyncSession):
       user= User(email= body.email,
             password_hash=hash_password(body.password),
             lastname=body.last_name,
             firstname=body.first_name)

       session.add(user)
       session.commit()
       session.refresh(user)
       return user
