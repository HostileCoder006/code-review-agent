from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
import uuid


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    review_id: uuid.UUID
    category: str
    severity: str
    evidence_level: str
    confidence: float
    title: str
    description: str
    hypothesis: str
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    function_name: Optional[str] = None
    evidence: list = []
    impact_analysis: Optional[dict] = None
    tests_generated: list = []
    tests_executed: list = []
    reproduction_status: str
    recommended_fix: Optional[str] = None
    fix_patch: Optional[str] = None
    verification_status: str
    github_comment_id: Optional[int] = None
    posted_to_github: bool
    self_review_notes: Optional[str] = None
    discarded_reason: Optional[str] = None
    created_at: datetime
