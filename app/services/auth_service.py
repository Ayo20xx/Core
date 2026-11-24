from sqlalchemy import exc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EmailException
from app.core.security import hash_password
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.schemas.user import UsersCreate


class AuthService:
 

    def __init__(self, repository: AuthRepository | None = None):
        self.repository = repository or AuthRepository()

    async def register(self, session: AsyncSession, body: UsersCreate) -> User:
 
        email = body.email.strip().lower()

        # 2. Check if email already exists
        if await self.repository.exists(session, email=email):
            raise EmailException("This email is already registered.")

        # 3. Hash password
        password_hash = hash_password(body.password)

        # 4. Build User model
        user = User(
            email=email,
            password_hash=password_hash,
            first_name=body.first_name,
            last_name=body.last_name,
            email_verified_at=None,
            is_active=True,
        )

        try:
            return await self.repository.add(session, user)
        except exc.IntegrityError as error:
            await session.rollback()
            raise EmailException("Email already taken.") from error