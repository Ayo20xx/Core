from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.auth import redis_client
from app.core.security import hash_password
from app.db.session import SessionLocal, engine, get_session
from app.main import app
from app.models.auth_session import UserSession
from app.models.user import User

REFRESH_COOKIE_NAME = "core_refresh_token"


@pytest.mark.asyncio
async def test_login_rotates_refresh_token_and_detects_reuse():
    await engine.dispose()
    await redis_client.aclose()
    email = f"{uuid4().hex}@example.com"
    password = "correct horse battery staple"
    async with SessionLocal() as db:
        user = User(
            email=email,
            first_name="Test",
            last_name="Customer",
            password_hash=hash_password(password),
            email_verified_at=datetime.now(UTC),
            is_active=True,
        )
        db.add(user)
        await db.commit()
        user_id = user.id

    async def override_session():
        async with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password,
                    "device_name": "test browser",
                },
                headers={"user-agent": "CORE auth integration test"},
            )
            assert login.status_code == 200
            assert "access_token" in login.json()
            first_refresh_token = login.cookies.get(REFRESH_COOKIE_NAME)
            assert first_refresh_token
            cookie = login.headers["set-cookie"].lower()
            assert "httponly" in cookie
            assert "secure" not in cookie
            assert first_refresh_token not in login.text

            first_access_token = login.json()["access_token"]
            sessions = await client.get(
                "/api/v1/auth/sessions",
                headers={"Authorization": f"Bearer {first_access_token}"},
            )
            assert sessions.status_code == 200
            assert len(sessions.json()) == 1
            assert sessions.json()[0]["device_name"] == "test browser"
            assert sessions.json()[0]["user_agent"] == "CORE auth integration test"
            session_id = sessions.json()[0]["id"]

            rotated = await client.post("/api/v1/auth/refresh")
            assert rotated.status_code == 200
            second_refresh_token = rotated.cookies.get(REFRESH_COOKIE_NAME)
            assert second_refresh_token
            assert second_refresh_token != first_refresh_token
            second_access_token = rotated.json()["access_token"]

            replay = await client.post(
                "/api/v1/auth/refresh",
                headers={"Cookie": f"{REFRESH_COOKIE_NAME}={first_refresh_token}"},
            )
            assert replay.status_code == 401
            assert "reuse detected" in replay.json()["detail"]

            revoked_access = await client.get(
                "/api/v1/auth/sessions",
                headers={"Authorization": f"Bearer {second_access_token}"},
            )
            assert revoked_access.status_code == 401

            async with SessionLocal() as db:
                session_row = await db.get(UserSession, session_id)
                assert session_row is not None
                assert session_row.revoked_at is not None
    finally:
        app.dependency_overrides.pop(get_session, None)
        async with SessionLocal() as db:
            user = await db.get(User, user_id)
            if user is not None:
                await db.delete(user)
                await db.commit()
        await engine.dispose()
        await redis_client.aclose()


@pytest.mark.asyncio
async def test_device_sessions_can_be_listed_and_revoked_independently():
    await engine.dispose()
    await redis_client.aclose()
    email = f"{uuid4().hex}@example.com"
    password = "correct horse battery staple"
    async with SessionLocal() as db:
        user = User(
            email=email,
            first_name="Test",
            last_name="Customer",
            password_hash=hash_password(password),
            email_verified_at=datetime.now(UTC),
            is_active=True,
        )
        db.add(user)
        await db.commit()
        user_id = user.id

    async def override_session():
        async with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            browser_login = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password,
                    "device_name": "browser",
                },
            )
            phone_login = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password,
                    "device_name": "phone",
                },
            )
            browser_access = browser_login.json()["access_token"]
            phone_access = phone_login.json()["access_token"]
            phone_auth = {"Authorization": f"Bearer {phone_access}"}

            sessions = await client.get("/api/v1/auth/sessions", headers=phone_auth)
            assert sessions.status_code == 200
            assert len(sessions.json()) == 2
            session_ids = {
                item["device_name"]: item["id"] for item in sessions.json()
            }
            assert next(item for item in sessions.json() if item["device_name"] == "phone")[
                "is_current"
            ]

            revoked = await client.delete(
                f"/api/v1/auth/sessions/{session_ids['browser']}",
                headers=phone_auth,
            )
            assert revoked.status_code == 204

            browser_request = await client.get(
                "/api/v1/auth/sessions",
                headers={"Authorization": f"Bearer {browser_access}"},
            )
            assert browser_request.status_code == 401
            phone_request = await client.get(
                "/api/v1/auth/sessions",
                headers=phone_auth,
            )
            assert phone_request.status_code == 200

            logout = await client.post("/api/v1/auth/logout", headers=phone_auth)
            assert logout.status_code == 204
            phone_request = await client.get(
                "/api/v1/auth/sessions",
                headers=phone_auth,
            )
            assert phone_request.status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)
        async with SessionLocal() as db:
            user = await db.get(User, user_id)
            if user is not None:
                await db.delete(user)
                await db.commit()
        await engine.dispose()
        await redis_client.aclose()


@pytest.mark.asyncio
async def test_login_rejects_unverified_user():
    await engine.dispose()
    await redis_client.aclose()
    email = f"{uuid4().hex}@example.com"
    password = "correct horse battery staple"
    async with SessionLocal() as db:
        user = User(
            email=email,
            first_name="Test",
            last_name="Customer",
            password_hash=hash_password(password),
            email_verified_at=None,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        user_id = user.id

    async def override_session():
        async with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )
            assert response.status_code == 403
            assert response.json()["detail"] == "Verify your email before logging in"
    finally:
        app.dependency_overrides.pop(get_session, None)
        async with SessionLocal() as db:
            user = await db.get(User, user_id)
            if user is not None:
                await db.delete(user)
                await db.commit()
        await engine.dispose()
        await redis_client.aclose()
