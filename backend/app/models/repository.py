import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    github_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    installation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    reviews: Mapped[list["Review"]] = relationship(back_populates="repository", cascade="all, delete-orphan")  # noqa: F821
