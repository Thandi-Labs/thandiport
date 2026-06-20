import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_superuser
from app.core.exceptions import CredentialsException
from app.core.security import hash_password, verify_password
from app.database import get_db
from app.models.audit_log import AuditAction
from app.models.user import User
from app.schemas.user import ChangePasswordRequest, UserAdminUpdate, UserRead, UserUpdate
from app.services import audit_service, email_service, user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    updated = await user_service.update_user(db, current_user, payload)
    await audit_service.log_action(
        db,
        action=AuditAction.USER_UPDATE,
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(current_user.id),
        status_code=200,
        request=request,
    )
    return updated


@router.post("/me/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise CredentialsException("Current password is incorrect")

    current_user.hashed_password = hash_password(payload.new_password)
    await db.flush()

    await audit_service.log_action(
        db,
        action=AuditAction.PASSWORD_CHANGE,
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(current_user.id),
        status_code=200,
        request=request,
    )
    await email_service.send_password_changed_email(
        to_email=current_user.email,
        username=current_user.username,
    )
    return {"message": "Password changed successfully"}


# ── Admin endpoints ────────────────────────────────────────────────────────────

@router.get("/", response_model=list[UserRead], dependencies=[Depends(require_superuser)])
async def list_users(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    result = await db.execute(select(User).limit(limit).offset(offset))
    return list(result.scalars().all())


@router.get("/{user_id}", response_model=UserRead, dependencies=[Depends(require_superuser)])
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> User:
    return await user_service.get_user_by_id(db, user_id)


@router.patch("/{user_id}", response_model=UserRead)
async def admin_update_user(
    user_id: uuid.UUID,
    payload: UserAdminUpdate,
    request: Request,
    admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await user_service.get_user_by_id(db, user_id)
    updated = await user_service.admin_update_user(db, user, payload)
    await audit_service.log_action(
        db,
        action=AuditAction.ADMIN_USER_UPDATE,
        user_id=admin.id,
        resource_type="user",
        resource_id=str(user_id),
        status_code=200,
        request=request,
        metadata=payload.model_dump(exclude_none=True),
    )
    return updated
