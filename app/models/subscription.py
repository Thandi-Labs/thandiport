import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class AccessStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    cancelled = "cancelled"
    suspended = "suspended"


class UserServiceAccess(Base):
    __tablename__ = "user_service_accesses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[AccessStatus] = mapped_column(
        Enum(AccessStatus), default=AccessStatus.active, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Reference ID from the payments service
    external_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="service_accesses", foreign_keys=[user_id])  # type: ignore[name-defined]  # noqa: F821
    service: Mapped["Service"] = relationship(back_populates="user_accesses")  # type: ignore[name-defined]  # noqa: F821
    granted_by: Mapped["User | None"] = relationship(foreign_keys=[granted_by_id])  # type: ignore[name-defined]  # noqa: F821
