"""
Dashboard statistics endpoint.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
import structlog

from app.core.database import get_db
from app.models.review import Review, ReviewStatus
from app.models.finding import Finding, EvidenceLevel, Severity

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/dashboard")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    # Review counts by status
    review_stats = await db.execute(
        select(Review.status, func.count(Review.id)).group_by(Review.status)
    )
    review_by_status = {row[0]: row[1] for row in review_stats}

    # Finding counts by severity
    finding_severity = await db.execute(
        select(Finding.severity, func.count(Finding.id))
        .where(Finding.evidence_level != EvidenceLevel.discarded)
        .group_by(Finding.severity)
    )
    findings_by_severity = {row[0]: row[1] for row in finding_severity}

    # Finding counts by evidence level
    finding_evidence = await db.execute(
        select(Finding.evidence_level, func.count(Finding.id)).group_by(Finding.evidence_level)
    )
    findings_by_evidence = {row[0]: row[1] for row in finding_evidence}

    # Average confidence
    avg_conf = await db.execute(
        select(func.avg(Finding.confidence))
        .where(Finding.evidence_level != EvidenceLevel.discarded)
    )
    avg_confidence = float(avg_conf.scalar() or 0)

    # Total reviews
    total_reviews = await db.execute(select(func.count(Review.id)))
    total = int(total_reviews.scalar() or 0)

    # Average review duration (minutes)
    duration_query = await db.execute(
        select(
            func.avg(
                func.extract("epoch", Review.completed_at - Review.started_at) / 60
            )
        ).where(
            Review.completed_at.isnot(None),
            Review.started_at.isnot(None),
        )
    )
    avg_duration_min = float(duration_query.scalar() or 0)

    return {
        "total_reviews": total,
        "reviews_by_status": review_by_status,
        "findings_by_severity": findings_by_severity,
        "findings_by_evidence_level": findings_by_evidence,
        "average_confidence": round(avg_confidence, 3),
        "average_review_duration_minutes": round(avg_duration_min, 1),
        "reproduced_findings": findings_by_evidence.get(EvidenceLevel.reproduced, 0),
        "discarded_findings": findings_by_evidence.get(EvidenceLevel.discarded, 0),
    }
