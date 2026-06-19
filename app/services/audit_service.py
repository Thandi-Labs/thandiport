import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog


async def log_action(
    db: AsyncSession,
    *,
    action: AuditAction,
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status_code: int | None = None,
    metadata: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    ip_address: str | None = None
    user_agent: str | None = None

    if request is not None:
        forwarded_for = request.headers.get("X-Forwarded-For")
        ip_address = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")

    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=user_agent,
        status_code=status_code,
        metadata_=metadata,
    )
    db.add(entry)
    # Flush without committing — the outer request transaction commits it.
    await db.flush()
    return entry
