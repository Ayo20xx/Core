import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.v1 import auth
from app.schemas.user import VerificationCodeCreate


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.expired: set[str] = set()
        self.lock = asyncio.Lock()
        self.fail = False

    def _check(self):
        if self.fail:
            raise RedisConnectionError("Redis unavailable")

    async def setex(self, key: str, seconds: int, value: str):
        self._check()
        self.values[key] = value
        self.expirations[key] = seconds
        self.expired.discard(key)

    async def get(self, key: str):
        self._check()
        if key in self.expired:
            return None
        return self.values.get(key)

    async def getdel(self, key: str):
        self._check()
        async with self.lock:
            return self.values.pop(key, None)

    async def incr(self, key: str):
        self._check()
        self.values[key] = str(int(self.values.get(key, "0")) + 1)
        return int(self.values[key])

    async def expire(self, key: str, seconds: int):
        self._check()
        self.expirations[key] = seconds

    async def delete(self, *keys: str):
        self._check()
        for key in keys:
            self.values.pop(key, None)
            self.expirations.pop(key, None)
            self.expired.discard(key)


class FakeSession:
    def __init__(self):
        self.commits = 0

    def add(self, _item):
        pass

    async def commit(self):
        self.commits += 1

    async def refresh(self, _item):
        pass


class FakeRepository:
    def __init__(self, user):
        self.user = user

    async def get_by_email(self, _session, email: str):
        return self.user if self.user.email == email else None


class FakeMail:
    codes: list[str] = []
    fail = False

    async def send_verification_code(self, _email: str, code: str):
        if self.fail:
            raise ValueError("SMTP unavailable")
        self.codes.append(code)


def make_user():
    return SimpleNamespace(
        id="895548c7-779a-4db4-bcb1-2dbd73f0c050",
        email="customer@example.com",
        first_name="Test",
        last_name="Customer",
        email_verified_at=None,
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def verification_setup(monkeypatch):
    redis = FakeRedis()
    session = FakeSession()
    user = make_user()
    FakeMail.codes = []
    FakeMail.fail = False
    monkeypatch.setattr(auth, "redis_client", redis)
    monkeypatch.setattr(auth, "MailService", FakeMail)
    monkeypatch.setattr(auth, "AuthRepository", lambda: FakeRepository(user))
    return redis, session, user


@pytest.mark.asyncio
async def test_register_and_verify_successfully(monkeypatch, verification_setup):
    redis, session, user = verification_setup
    monkeypatch.setattr(auth, "AuthService", lambda: SimpleNamespace(
        register=_return_user(user)
    ))

    result = await auth.register(session, SimpleNamespace(email=user.email))

    assert result.email == user.email
    assert len(FakeMail.codes) == 1
    code = FakeMail.codes[0]
    assert len(code) == 6 and code.isascii() and code.isdecimal()
    assert await redis.get(f"verification:code:{user.email}") is not None
    assert redis.expirations[f"verification:code:{user.email}"] == auth.CODE_TTL_SECONDS

    verified = await auth.verify_code(
        session,
        VerificationCodeCreate(email=user.email, code=code),
    )
    assert verified.email_verified_at is not None
    assert session.commits == 1
    assert await redis.get(f"verification:code:{user.email}") is None


def _return_user(user):
    async def register(_session, _body):
        return user

    return register


@pytest.mark.asyncio
async def test_expired_code_is_rejected(verification_setup):
    redis, session, user = verification_setup
    key = f"verification:code:{user.email}"
    await redis.setex(key, auth.CODE_TTL_SECONDS, PasswordHasher().hash("123456"))
    redis.expired.add(key)

    with pytest.raises(HTTPException) as error:
        await auth.verify_code(
            session,
            VerificationCodeCreate(email=user.email, code="123456"),
        )
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_wrong_code_locks_after_five_attempts(verification_setup):
    redis, session, user = verification_setup
    await redis.setex(
        f"verification:code:{user.email}",
        auth.CODE_TTL_SECONDS,
        PasswordHasher().hash("123456"),
    )

    for _ in range(4):
        with pytest.raises(HTTPException) as error:
            await auth.verify_code(
                session,
                VerificationCodeCreate(email=user.email, code="000000"),
            )
        assert error.value.status_code == 400

    with pytest.raises(HTTPException) as error:
        await auth.verify_code(
            session,
            VerificationCodeCreate(email=user.email, code="000000"),
        )
    assert error.value.status_code == 429
    assert await redis.get(f"verification:code:{user.email}") is None


@pytest.mark.asyncio
async def test_used_code_cannot_be_replayed(verification_setup):
    redis, session, user = verification_setup
    code = "012345"
    await redis.setex(
        f"verification:code:{user.email}",
        auth.CODE_TTL_SECONDS,
        PasswordHasher().hash(code),
    )
    payload = VerificationCodeCreate(email=user.email, code=code)

    await auth.verify_code(session, payload)
    with pytest.raises(HTTPException) as error:
        await auth.verify_code(session, payload)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_resend_invalidates_previous_code(verification_setup):
    redis, session, user = verification_setup
    old_code = "111111"
    await redis.setex(
        f"verification:code:{user.email}",
        auth.CODE_TTL_SECONDS,
        PasswordHasher().hash(old_code),
    )

    result = await auth.resend_verification_code(
        session,
        SimpleNamespace(email=user.email),
    )

    assert result["detail"] == "Verification email sent"
    new_code = FakeMail.codes[-1]
    assert new_code != old_code
    with pytest.raises(HTTPException):
        await auth.verify_code(
            session,
            VerificationCodeCreate(email=user.email, code=old_code),
        )
    await auth.verify_code(
        session,
        VerificationCodeCreate(email=user.email, code=new_code),
    )


@pytest.mark.asyncio
async def test_concurrent_verification_only_succeeds_once(verification_setup):
    redis, session, user = verification_setup
    code = "123456"
    await redis.setex(
        f"verification:code:{user.email}",
        auth.CODE_TTL_SECONDS,
        PasswordHasher().hash(code),
    )
    payload = VerificationCodeCreate(email=user.email, code=code)

    outcomes = await asyncio.gather(
        auth.verify_code(session, payload),
        auth.verify_code(session, payload),
        return_exceptions=True,
    )
    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, HTTPException) for outcome in outcomes) == 1


@pytest.mark.asyncio
async def test_smtp_failure_keeps_account_but_does_not_leave_code(monkeypatch, verification_setup):
    redis, session, user = verification_setup
    FakeMail.fail = True
    monkeypatch.setattr(auth, "AuthService", lambda: SimpleNamespace(
        register=_return_user(user)
    ))

    with pytest.raises(HTTPException) as error:
        await auth.register(session, SimpleNamespace(email=user.email))
    assert error.value.status_code == 503
    assert await redis.get(f"verification:code:{user.email}") is None


@pytest.mark.asyncio
async def test_redis_outage_returns_service_unavailable(verification_setup):
    redis, session, user = verification_setup
    redis.fail = True

    with pytest.raises(HTTPException) as error:
        await auth.verify_code(
            session,
            VerificationCodeCreate(email=user.email, code="123456"),
        )
    assert error.value.status_code == 503


def test_verification_code_requires_six_ascii_digits():
    for code in ("12345", "1234567", "12a456", "１２３４５６"):
        with pytest.raises(ValidationError):
            VerificationCodeCreate(email="customer@example.com", code=code)
