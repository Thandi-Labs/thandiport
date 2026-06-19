from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_superuser
from app.database import get_db
from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogFilter, AuditLogRead

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=list[AuditLogRead])
async def get_audit_logs(
    filters: AuditLogFilter = Depends(),
    admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.created_at.desc())

    if filters.user_id:
        query = query.where(AuditLog.user_id == filters.user_id)
    if filters.action:
        query = query.where(AuditLog.action == filters.action)
    if filters.resource_type:
        query = query.where(AuditLog.resource_type == filters.resource_type)
    if filters.from_date:
        query = query.where(AuditLog.created_at >= filters.from_date)
    if filters.to_date:
        query = query.where(AuditLog.created_at <= filters.to_date)

    query = query.limit(filters.limit).offset(filters.offset)
    result = await db.execute(query)
    return list(result.scalars().all())
