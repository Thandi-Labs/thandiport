from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_internal_api_key
from app.core.exceptions import CredentialsException
from app.core.security import (
    blacklist_jti,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import get_db, get_redis
from app.models.audit_log import AuditAction
from app.models.user import User
from app.schemas.token import RefreshTokenRequest, TokenPair, VerifyTokenRequest, VerifyTokenResponse
from app.schemas.user import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserCreate,
    UserRead,
)
from app.services import audit_service, auth_service, user_service
from app.services.auth_service import revoke_all_user_tokens

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> User:
    user = await user_service.create_user(db, payload)
    await audit_service.log_action(
        db,
        action=AuditAction.REGISTER,
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        status_code=201,
        request=request,
    )
    return user


@router.post("/login", response_model=TokenPair)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TokenPair:
    user = await auth_service.authenticate_user(db, form_data.username, form_data.password)
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    tokens = await auth_service.issue_token_pair(
        db, user, ip_address=ip, device_info=request.headers.get("User-Agent")
    )
    await audit_service.log_action(
        db,
        action=AuditAction.LOGIN,
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        status_code=200,
        request=request,
    )
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshTokenRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> None:
    from fastapi.security import HTTPBearer
    from fastapi import Request as FastAPIRequest

    # Blacklist the current access token's JTI
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header.split(" ", 1)[1]
        try:
            decoded = decode_access_token(raw_token)
            jti = decoded.get("jti", "")
            exp = decoded.get("exp", 0)
            ttl = max(0, int(exp - datetime.now(UTC).timestamp()))
            if jti and ttl > 0:
                await blacklist_jti(redis, jti, ttl)
        except JWTError:
            pass

    await auth_service.revoke_refresh_token(db, payload.refresh_token)
    await audit_service.log_action(
        db,
        action=AuditAction.LOGOUT,
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(current_user.id),
        status_code=204,
        request=request,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    payload: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TokenPair:
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    tokens = await auth_service.refresh_access_token(db, payload.refresh_token, ip_address=ip)

    # Decode to get user_id for audit log
    try:
        decoded = decode_access_token(tokens.access_token)
        user_id = decoded.get("sub")
        from uuid import UUID
        await audit_service.log_action(
            db,
            action=AuditAction.TOKEN_REFRESH,
            user_id=UUID(user_id) if user_id else None,
            resource_type="token",
            status_code=200,
            request=request,
        )
    except (JWTError, ValueError):
        pass

    return tokens


@router.post("/verify-token", response_model=VerifyTokenResponse)
async def verify_token(
    payload: VerifyTokenRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: None = Depends(require_internal_api_key),
) -> VerifyTokenResponse:
    """
    Internal endpoint for other thandilabs services to verify a user's token
    and optionally check access to a specific service.
    Requires the X-Internal-API-Key header.
    """
    from sqlalchemy import select
    from app.models.user import User as UserModel
    from app.models.subscription import UserServiceAccess, AccessStatus
    from app.models.service import Service
    from app.schemas.user import UserRead

    try:
        decoded = decode_access_token(payload.token)
    except JWTError:
        return VerifyTokenResponse(valid=False, message="Invalid or expired token")

    jti = decoded.get("jti", "")
    if await redis.exists(f"blacklisted_jti:{jti}"):
        return VerifyTokenResponse(valid=False, message="Token has been revoked")

    user_id = decoded.get("sub")
    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return VerifyTokenResponse(valid=False, message="User not found or inactive")

    user_read = UserRead.model_validate(user)
    response = VerifyTokenResponse(valid=True, user=user_read)

    if payload.service_slug:
        svc_result = await db.execute(
            select(Service).where(Service.slug == payload.service_slug, Service.is_active == True)  # noqa: E712
        )
        service = svc_result.scalar_one_or_none()

        if service is None:
            response.has_service_access = False
            response.message = "Service not found"
        elif not service.requires_subscription:
            response.has_service_access = True
        else:
            from datetime import UTC, datetime
            access_result = await db.execute(
                select(UserServiceAccess).where(
                    UserServiceAccess.user_id == user.id,
                    UserServiceAccess.service_id == service.id,
                    UserServiceAccess.status == AccessStatus.active,
                )
            )
            access = access_result.scalar_one_or_none()
            if access and (access.expires_at is None or access.expires_at.replace(tzinfo=UTC) > datetime.now(UTC)):
                response.has_service_access = True
            else:
                response.has_service_access = False

    return response


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict[str, str]:
    """
    Always returns 200 regardless of whether the email exists,
    to avoid leaking user enumeration information.
    In production, send the token via email. Here it's returned directly for development.
    """
    reset_token = await auth_service.initiate_password_reset(db, redis, payload.email)
    await audit_service.log_action(
        db,
        action=AuditAction.PASSWORD_RESET_REQUEST,
        resource_type="user",
        status_code=200,
        request=request,
        metadata={"email": payload.email},
    )
    response: dict[str, str] = {"message": "If that email exists, a reset link has been sent"}
    if reset_token and settings.APP_ENV == "development":
        response["reset_token"] = reset_token
    return response


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict[str, str]:
    user = await auth_service.complete_password_reset(db, redis, payload.token, payload.new_password)
    await audit_service.log_action(
        db,
        action=AuditAction.PASSWORD_RESET,
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        status_code=200,
        request=request,
    )
    return {"message": "Password has been reset successfully"}
