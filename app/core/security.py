import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import redis.asyncio as aioredis
from jose import JWTError, jwt

from app.config import settings

ACCESS_TOKEN_PREFIX = "access_token:"
BLACKLIST_PREFIX = "blacklisted_jti:"
RESET_TOKEN_PREFIX = "password_reset:"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def hash_token(token: str) -> str:
    """SHA-256 hash a token before storing it — tokens are secrets, not IDs."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    jti = secrets.token_urlsafe(16)
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "jti": jti,
        "iat": datetime.now(UTC),
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token() -> str:
    """Returns a cryptographically random opaque token string."""
    return secrets.token_urlsafe(64)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token. Raises JWTError on failure."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("type") != "access":
        raise JWTError("Not an access token")
    return payload


def create_password_reset_token(user_id: str) -> str:
    """Returns a short-lived JWT for password reset (not stored in DB, stored in Redis)."""
    expire = datetime.now(UTC) + timedelta(minutes=30)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "password_reset",
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_password_reset_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("type") != "password_reset":
        raise JWTError("Not a password reset token")
    return payload


async def blacklist_jti(redis: aioredis.Redis, jti: str, expires_in_seconds: int) -> None:
    """Add a JTI to the Redis blacklist so the token cannot be reused after logout."""
    await redis.setex(f"{BLACKLIST_PREFIX}{jti}", expires_in_seconds, "1")


async def is_jti_blacklisted(redis: aioredis.Redis, jti: str) -> bool:
    return bool(await redis.exists(f"{BLACKLIST_PREFIX}{jti}"))


async def store_reset_token(redis: aioredis.Redis, user_id: str, jti: str) -> None:
    """Track that a reset token was issued for this user. Allows single-use enforcement."""
    await redis.setex(f"{RESET_TOKEN_PREFIX}{user_id}", 1800, jti)


async def consume_reset_token(redis: aioredis.Redis, user_id: str, jti: str) -> bool:
    """Return True and delete the key if the jti matches (single-use)."""
    key = f"{RESET_TOKEN_PREFIX}{user_id}"
    stored = await redis.get(key)
    if stored == jti:
        await redis.delete(key)
        return True
    return False
