import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class AuditAction(str, enum.Enum):
    # Auth actions
    REGISTER = "register"
    LOGIN = "login"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET = "password_reset"
    # User actions
    USER_UPDATE = "user_update"
    USER_ACTIVATE = "user_activate"
    USER_DEACTIVATE = "user_deactivate"
    # Access actions
    ACCESS_GRANT = "access_grant"
    ACCESS_REVOKE = "access_revoke"
    ACCESS_CHECK = "access_check"
    # Admin actions
    ADMIN_USER_UPDATE = "admin_user_update"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    user: Mapped["User | None"] = relationship(back_populates="audit_logs")  # type: ignore[name-defined]  # noqa: F821
