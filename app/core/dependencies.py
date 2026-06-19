from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import Depends, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import CredentialsException, PermissionDeniedException
from app.core.security import decode_access_token, is_jti_blacklisted
from app.database import get_db, get_redis
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-Internal-API-Key", auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> User:
    if credentials is None:
        raise CredentialsException("No bearer token provided")

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise CredentialsException("Invalid or expired token")

    jti: str = payload.get("jti", "")
    if await is_jti_blacklisted(redis, jti):
        raise CredentialsException("Token has been revoked")

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise CredentialsException("Token missing subject")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise CredentialsException("User not found")
    if not user.is_active:
        raise CredentialsException("User account is disabled")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


async def require_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_superuser:
        raise PermissionDeniedException("Superuser access required")
    return current_user


async def require_internal_api_key(
    api_key: str | None = Security(api_key_header),
) -> None:
    """Validates the shared internal API key used by other thandilabs services."""
    if api_key is None or api_key != settings.INTERNAL_SERVICE_API_KEY:
        raise PermissionDeniedException("Invalid or missing internal API key")
