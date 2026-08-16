import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Installation(Base):
    __tablename__ = "installations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    installation_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    account_login: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(String(50))  # "User" or "Organization"
    access_token: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
