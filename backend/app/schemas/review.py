from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
import uuid

from app.schemas.finding import FindingOut
from app.schemas.repository import RepositoryOut


class ReviewListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pr_number: int
    pr_title: str
    pr_author: str
    pr_url: str
    status: str
    files_analyzed: int
    functions_impacted: int
    tests_generated: int
    tests_executed: int
    findings_verified: int
    findings_discarded: int
    confidence: float
    created_at: datetime
    completed_at: Optional[datetime] = None
    repository: RepositoryOut


class ReviewOut(ReviewListOut):
    base_sha: str
    head_sha: str
    impact_map: Optional[dict] = None
    error_message: Optional[str] = None


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    actor: str
    message: str
    details: Optional[dict] = None
    created_at: datetime


class ReviewDetailOut(ReviewOut):
    findings: list[FindingOut] = []
    timeline: list[TimelineEventOut] = []
