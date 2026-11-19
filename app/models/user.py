import sqlalchemy
from app.db.base import Base 
from uuid import UUID
from pydantic import EmailStr
from datetime import datetime


class Users(Base):
    __tablename__ = "Users"
    id : UUID 
    email : EmailStr
    first_name : str 
    last_name :  str 
    password_hash : str 
    email_verified_at : datetime
    is_active : bool
    created_at : datetime
    updated_at : datetime 


