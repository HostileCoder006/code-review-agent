import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, func, ForeignKey, Enum, JSON, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Severity(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class EvidenceLevel(str, enum.Enum):
    potential = "potential"
    evidence_backed = "evidence_backed"
    reproduced = "reproduced"
    fixed_and_verified = "fixed_and_verified"
    discarded = "discarded"


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id"), index=True)

    # Classification
    category: Mapped[str] = mapped_column(String(100))   # bug, security, performance, etc.
    severity: Mapped[Severity] = mapped_column(Enum(Severity))
    evidence_level: Mapped[EvidenceLevel] = mapped_column(Enum(EvidenceLevel))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # Description
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text)
    hypothesis: Mapped[str] = mapped_column(Text)

    # Location
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    function_name: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Evidence
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    impact_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Tests
    tests_generated: Mapped[list] = mapped_column(JSON, default=list)
    tests_executed: Mapped[list] = mapped_column(JSON, default=list)
    reproduction_status: Mapped[str] = mapped_column(String(50), default="not_attempted")

    # Fix
    recommended_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="not_attempted")

    # GitHub
    github_comment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posted_to_github: Mapped[bool] = mapped_column(Boolean, default=False)

    # Self-review
    self_review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    discarded_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    review: Mapped["Review"] = relationship(back_populates="findings")  # noqa: F821
