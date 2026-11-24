from datetime import UTC, datetime, timedelta
import secrets
import string

from redis.asyncio import Redis as RedisClient

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.exceptions import EmailException
from app.repositories.auth_repository import AuthRepository
from app.schemas.user import UsersCreate
from app.models.verification_code import VerificationCode
from app.services.mail_service import MailService

redis_client = RedisClient.from_url("redis://localhost:6379/0", decode_responses=True)


class VerificationService:
    def __init__(self, repository: AuthRepository | None = None):
        self.repository = repository or AuthRepository()
        self.hasher = PasswordHasher()
        self.mail_service = MailService()

    async def generate_and_store_code(self, session, email: str) -> str:
        """Generate a 6-digit code, store it in Redis, and send via email."""
        email = email.strip().lower()

        code = "".join(secrets.choice(string.digits) for _ in range(6))
        code_hash = self.hasher.hash(code)

        expires_at = datetime.now(UTC) + timedelta(minutes=15)

        # Store in Redis with TTL
        key = f"verification:code:{email}"
        await redis_client.setex(key, 900, code_hash)  # 15 min TTL

        # Also store in DB for persistence/backup
        code_row = VerificationCode(
            code=code,
            code_hash=code_hash,
            email=email,
            expires_at=expires_at,
            attempts=0,
        )
        session.add(code_row)
        await session.commit()
        await session.refresh(code_row)

        await self.mail_service.send_verification_code(email, code)

        return code

    async def verify_code(self, session, email: str, code: str) -> VerificationCode | None:
        """Verify a 6-digit code. Checks Redis first, then DB fallback."""
        email = email.strip().lower()

        # Check Redis first (primary)
        import hashlib
        code_hash = self.hasher.hash(code)
        key = f"verification:code:{email}"
        redis_hash = await redis_client.get(key)

        if redis_hash:
            # Verify against Redis stored hash
            try:
                self.hasher.verify(code, redis_hash)
                # Code valid - consume from Redis
                await redis_client.delete(key)
                # Also mark as used in DB
                await self._consume_code_db(session, email)
                return True
            except VerifyMismatchError:
                # Wrong code - increment attempts
                await redis_client.incr(f"verification:attempts:{email}")
                return None
        else:
            # Fallback to DB check
            statement = select(VerificationCode).where(VerificationCode.email == email)
            result = await session.execute(statement)
            code_row = result.scalar_one_or_none()

            if code_row is None or not code_row.is_valid():
                return None

            code_row.attempts += 1
            session.add(code_row)
            await session.commit()

            try:
                self.hasher.verify(code, code_row.code_hash)
            except VerifyMismatchError:
                code_row.attempts -= 1
                session.add(code_row)
                await session.commit()
                return None

            # Code valid - mark as used
            code_row.used_at = datetime.now(UTC)
            session.add(code_row)
            await session.commit()

            # Also consume from Redis if exists
            await redis_client.delete(f"verification:code:{email}")

            return code_row

    async def _consume_code_db(self, session, email: str):
        """Mark code as used in DB."""
        statement = select(VerificationCode).where(VerificationCode.email == email)
        result = await session.execute(statement)
        code_row = result.scalar_one_or_none()
        if code_row:
            code_row.used_at = datetime.now(UTC)
            session.add(code_row)
            await session.commit()

    async def resend_code(self, session, email: str) -> str:
        """Resend a new verification code, invalidating any previous ones."""
        email = email.strip().lower()

        # Invalidate existing Redis code
        await redis_client.delete(f"verification:code:{email}")

        # Invalidate existing DB codes
        statement = select(VerificationCode).where(VerificationCode.email == email)
        result = await session.execute(statement)
        existing = result.scalars().all()
        for row in existing:
            await session.delete(row)
        await session.commit()

        return await self.generate_and_store_code(session, email)