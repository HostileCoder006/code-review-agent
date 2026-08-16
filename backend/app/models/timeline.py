import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100))   # e.g. "pr_received", "test_executed"
    actor: Mapped[str] = mapped_column(String(100))         # e.g. "orchestrator", "security_agent"
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    review: Mapped["Review"] = relationship(back_populates="timeline")  # noqa: F821
