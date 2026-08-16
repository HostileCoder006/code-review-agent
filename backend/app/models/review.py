import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, func, ForeignKey, Enum, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    indexing = "indexing"
    investigating = "investigating"
    verifying = "verifying"
    self_review = "self_review"
    publishing = "publishing"
    completed = "completed"
    failed = "failed"


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), index=True)
    pr_number: Mapped[int] = mapped_column(Integer)
    pr_title: Mapped[str] = mapped_column(String(1024))
    pr_author: Mapped[str] = mapped_column(String(255))
    pr_url: Mapped[str] = mapped_column(String(1024))
    base_sha: Mapped[str] = mapped_column(String(40))
    head_sha: Mapped[str] = mapped_column(String(40))
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.pending, index=True
    )
    files_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    functions_impacted: Mapped[int] = mapped_column(Integer, default=0)
    tests_generated: Mapped[int] = mapped_column(Integer, default=0)
    tests_executed: Mapped[int] = mapped_column(Integer, default=0)
    findings_verified: Mapped[int] = mapped_column(Integer, default=0)
    findings_discarded: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    github_check_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_diff: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    impact_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    repository: Mapped["Repository"] = relationship(back_populates="reviews")  # noqa: F821
    findings: Mapped[list["Finding"]] = relationship(back_populates="review", cascade="all, delete-orphan")  # noqa: F821
    timeline: Mapped[list["TimelineEvent"]] = relationship(back_populates="review", cascade="all, delete-orphan", order_by="TimelineEvent.created_at")  # noqa: F821
