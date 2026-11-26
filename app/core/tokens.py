from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.config import auth_setting

JWT_ISSUER = "core"
JWT_ALGORITHM = "HS256"


def create_access_token(user_id: UUID, session_id: UUID) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=auth_setting.access_token_ttl_minutes)
    return jwt.encode(
        {
            "iss": JWT_ISSUER,
            "sub": str(user_id),
            "sid": str(session_id),
            "type": "access",
            "iat": now,
            "exp": expires_at,
        },
        auth_setting.jwt_secret_key.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, str | int]:
    claims = jwt.decode(
        token,
        auth_setting.jwt_secret_key.get_secret_value(),
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        options={"require": ["exp", "iat", "iss", "sid", "sub", "type"]},
    )
    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("Token is not an access token")
    return claims
