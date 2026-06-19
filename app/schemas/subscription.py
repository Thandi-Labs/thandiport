import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.subscription import AccessStatus
from app.schemas.service import ServiceRead


class GrantAccessRequest(BaseModel):
    user_id: uuid.UUID
    service_slug: str
    expires_at: datetime | None = None
    external_subscription_id: str | None = None


class RevokeAccessRequest(BaseModel):
    user_id: uuid.UUID
    service_slug: str


class UserServiceAccessCreate(BaseModel):
    user_id: uuid.UUID
    service_id: uuid.UUID
    expires_at: datetime | None = None
    external_subscription_id: str | None = None


class UserServiceAccessRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    service: ServiceRead
    status: AccessStatus
    expires_at: datetime | None
    external_subscription_id: str | None
    created_at: datetime


class AccessCheckResponse(BaseModel):
    has_access: bool
    service: ServiceRead
    access: UserServiceAccessRead | None = None
    reason: str | None = None
