import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.user import UserRead


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class VerifyTokenRequest(BaseModel):
    token: str
    service_slug: str | None = None  # optionally check access to a specific service


class VerifyTokenResponse(BaseModel):
    valid: bool
    user: UserRead | None = None
    has_service_access: bool | None = None
    message: str | None = None
