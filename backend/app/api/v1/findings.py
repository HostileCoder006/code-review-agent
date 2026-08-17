from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional
import structlog
import uuid

from app.core.database import get_db
from app.models.finding import Finding
from app.schemas.finding import FindingOut

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/", response_model=list[FindingOut])
async def list_findings(
    review_id: Optional[uuid.UUID] = Query(None),
    severity: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    evidence_level: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Finding).order_by(desc(Finding.created_at))
    if review_id:
        query = query.where(Finding.review_id == review_id)
    if severity:
        query = query.where(Finding.severity == severity)
    if category:
        query = query.where(Finding.category == category)
    if evidence_level:
        query = query.where(Finding.evidence_level == evidence_level)
    query = query.limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{finding_id}", response_model=FindingOut)
async def get_finding(finding_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding
