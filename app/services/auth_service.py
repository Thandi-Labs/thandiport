import uuid
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import CredentialsException
from app.core.security import (
    consume_reset_token,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_password_reset_token,
    hash_password,
    hash_token,
    store_reset_token,
    verify_password,
)
from app.models.token import RefreshToken
from app.models.user import User
from app.schemas.token import TokenPair


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise CredentialsException("Incorrect email or password")
    if not user.is_active:
        raise CredentialsException("Account is disabled")
    return user


async def issue_token_pair(
    db: AsyncSession,
    user: User,
    ip_address: str | None = None,
    device_info: str | None = None,
) -> TokenPair:
    access_token = create_access_token(str(user.id))
    refresh_token_value = create_refresh_token()

    token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token_value),
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=ip_address,
        device_info=device_info,
    )
    db.add(token_record)
    await db.flush()

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token_value,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def refresh_access_token(
    db: AsyncSession,
    refresh_token_value: str,
    ip_address: str | None = None,
) -> TokenPair:
    token_hash = hash_token(refresh_token_value)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked == False,  # noqa: E712
        )
    )
    token_record = result.scalar_one_or_none()

    if token_record is None:
        raise CredentialsException("Invalid refresh token")
    if token_record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise CredentialsException("Refresh token has expired")

    # Rotate: revoke old token and issue a fresh pair
    token_record.is_revoked = True
    await db.flush()

    user_result = await db.execute(select(User).where(User.id == token_record.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise CredentialsException("User not found or disabled")

    return await issue_token_pair(db, user, ip_address=ip_address)


async def revoke_refresh_token(db: AsyncSession, refresh_token_value: str) -> None:
    token_hash = hash_token(refresh_token_value)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_record = result.scalar_one_or_none()
    if token_record:
        token_record.is_revoked = True
        await db.flush()


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,  # noqa: E712
        )
    )
    for token in result.scalars().all():
        token.is_revoked = True
    await db.flush()


async def initiate_password_reset(
    db: AsyncSession, redis: aioredis.Redis, email: str
) -> str | None:
    """Returns a reset token if the user exists, else None (don't reveal existence)."""
    from app.core.security import create_password_reset_token
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return None

    token = create_password_reset_token(str(user.id))
    try:
        payload = decode_password_reset_token(token)
        await store_reset_token(redis, str(user.id), payload["jti"])
    except JWTError:
        pass
    return token


async def complete_password_reset(
    db: AsyncSession, redis: aioredis.Redis, token: str, new_password: str
) -> User:
    try:
        payload = decode_password_reset_token(token)
    except JWTError:
        raise CredentialsException("Invalid or expired reset token")

    user_id = payload.get("sub")
    jti = payload.get("jti", "")

    if not await consume_reset_token(redis, user_id, jti):
        raise CredentialsException("Reset token already used or expired")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise CredentialsException("User not found")

    user.hashed_password = hash_password(new_password)
    await revoke_all_user_tokens(db, user.id)
    await db.flush()
    return user
