import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.audit_log import AuditAction


class AuditLogRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID | None
    action: AuditAction
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    user_agent: str | None
    status_code: int | None
    metadata_: dict[str, Any] | None
    created_at: datetime


class AuditLogFilter(BaseModel):
    user_id: uuid.UUID | None = None
    action: AuditAction | None = None
    resource_type: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    limit: int = 50
    offset: int = 0
