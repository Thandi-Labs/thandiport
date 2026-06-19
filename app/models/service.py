from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Service(Base):
    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_subscription: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user_accesses: Mapped[list["UserServiceAccess"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="service", cascade="all, delete-orphan"
    )
