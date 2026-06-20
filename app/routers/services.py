import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_internal_api_key, require_superuser
from app.core.exceptions import ConflictException, NotFoundException
from app.database import get_db
from app.models.audit_log import AuditAction
from app.models.service import Service
from app.models.subscription import AccessStatus, UserServiceAccess
from app.models.user import User
from app.schemas.service import ServiceCreate, ServiceRead, ServiceUpdate
from app.schemas.subscription import (
    AccessCheckResponse,
    GrantAccessRequest,
    RevokeAccessRequest,
    UserServiceAccessRead,
)
from app.services import audit_service

router = APIRouter(prefix="/services", tags=["services"])


async def _get_service_by_slug(db: AsyncSession, slug: str) -> Service:
    result = await db.execute(select(Service).where(Service.slug == slug))
    service = result.scalar_one_or_none()
    if service is None:
        raise NotFoundException(f"Service '{slug}' not found")
    return service


# ── Public / Authenticated ─────────────────────────────────────────────────────

@router.get("/", response_model=list[ServiceRead])
async def list_services(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Service]:
    result = await db.execute(select(Service).where(Service.is_active == True))  # noqa: E712
    return list(result.scalars().all())


@router.get("/{service_slug}/access", response_model=AccessCheckResponse)
async def check_my_access(
    service_slug: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccessCheckResponse:
    service = await _get_service_by_slug(db, service_slug)

    if not service.requires_subscription:
        svc_read = ServiceRead.model_validate(service)
        return AccessCheckResponse(
            has_access=True, service=svc_read, reason="Service is freely accessible"
        )

    access_result = await db.execute(
        select(UserServiceAccess).where(
            UserServiceAccess.user_id == current_user.id,
            UserServiceAccess.service_id == service.id,
            UserServiceAccess.status == AccessStatus.active,
        )
    )
    access = access_result.scalar_one_or_none()

    has_access = bool(
        access
        and (access.expires_at is None or access.expires_at.replace(tzinfo=UTC) > datetime.now(UTC))
    )

    await audit_service.log_action(
        db,
        action=AuditAction.ACCESS_CHECK,
        user_id=current_user.id,
        resource_type="service",
        resource_id=service_slug,
        status_code=200,
        request=request,
        metadata={"has_access": has_access},
    )

    return AccessCheckResponse(
        has_access=has_access,
        service=ServiceRead.model_validate(service),
        access=UserServiceAccessRead.model_validate(access) if access else None,
        reason=None if has_access else "No active subscription",
    )


# ── Admin / Internal ───────────────────────────────────────────────────────────

@router.post("/", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: ServiceCreate,
    admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> Service:
    existing = await db.execute(select(Service).where(Service.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise ConflictException(f"Service with slug '{payload.slug}' already exists")

    service = Service(**payload.model_dump())
    db.add(service)
    await db.flush()
    await db.refresh(service)
    return service


@router.patch("/{service_slug}", response_model=ServiceRead)
async def update_service(
    service_slug: str,
    payload: ServiceUpdate,
    admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> Service:
    service = await _get_service_by_slug(db, service_slug)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(service, field, value)
    await db.flush()
    await db.refresh(service)
    return service


@router.post("/grant-access", status_code=status.HTTP_201_CREATED, response_model=UserServiceAccessRead)
async def grant_access(
    payload: GrantAccessRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_internal_api_key),
) -> UserServiceAccess:
    """
    Called by the payments service (or an admin) to grant a user access to a service.
    Requires X-Internal-API-Key header.
    """
    service = await _get_service_by_slug(db, payload.service_slug)

    # Check if active access already exists; update it instead of duplicating
    existing = await db.execute(
        select(UserServiceAccess).where(
            UserServiceAccess.user_id == payload.user_id,
            UserServiceAccess.service_id == service.id,
        )
    )
    access = existing.scalar_one_or_none()

    if access:
        access.status = AccessStatus.active
        access.expires_at = payload.expires_at
        access.external_subscription_id = payload.external_subscription_id
    else:
        access = UserServiceAccess(
            user_id=payload.user_id,
            service_id=service.id,
            expires_at=payload.expires_at,
            external_subscription_id=payload.external_subscription_id,
        )
        db.add(access)

    await db.flush()
    await db.refresh(access)
    await audit_service.log_action(
        db,
        action=AuditAction.ACCESS_GRANT,
        user_id=payload.user_id,
        resource_type="service",
        resource_id=payload.service_slug,
        status_code=201,
        request=request,
        metadata={"external_subscription_id": payload.external_subscription_id},
    )
    return access


@router.post("/revoke-access", status_code=status.HTTP_200_OK)
async def revoke_access(
    payload: RevokeAccessRequest,
    request: Request,
    admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    service = await _get_service_by_slug(db, payload.service_slug)

    result = await db.execute(
        select(UserServiceAccess).where(
            UserServiceAccess.user_id == payload.user_id,
            UserServiceAccess.service_id == service.id,
            UserServiceAccess.status == AccessStatus.active,
        )
    )
    access = result.scalar_one_or_none()
    if not access:
        raise NotFoundException("No active access record found")

    access.status = AccessStatus.cancelled
    await db.flush()
    await audit_service.log_action(
        db,
        action=AuditAction.ACCESS_REVOKE,
        user_id=admin.id,
        resource_type="service",
        resource_id=payload.service_slug,
        status_code=200,
        request=request,
        metadata={"target_user_id": str(payload.user_id)},
    )
    return {"message": "Access revoked successfully"}
