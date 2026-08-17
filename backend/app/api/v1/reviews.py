"""
Review API endpoints — list, detail, timeline, SSE stream.
"""
import asyncio
import json
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
import structlog

from app.core.database import get_db
from app.core.redis import get_redis
from app.models.review import Review
from app.models.finding import Finding, EvidenceLevel
from app.schemas.review import ReviewOut, ReviewListOut, ReviewDetailOut

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/", response_model=list[ReviewListOut])
async def list_reviews(
    repository_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Review).options(selectinload(Review.repository)).order_by(desc(Review.created_at))

    if repository_id:
        query = query.where(Review.repository_id == repository_id)
    if status:
        query = query.where(Review.status == status)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    reviews = result.scalars().all()
    return reviews


@router.get("/{review_id}", response_model=ReviewDetailOut)
async def get_review(review_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Review)
        .options(
            selectinload(Review.repository),
            selectinload(Review.findings),
            selectinload(Review.timeline),
        )
        .where(Review.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@router.get("/{review_id}/timeline")
async def get_timeline(review_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Review)
        .options(selectinload(Review.timeline))
        .where(Review.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "actor": e.actor,
            "message": e.message,
            "details": e.details,
            "created_at": e.created_at.isoformat(),
        }
        for e in review.timeline
    ]


@router.get("/{review_id}/stream")
async def stream_timeline(review_id: uuid.UUID):
    """Server-sent events stream for real-time investigation updates."""
    async def event_generator():
        r = get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(f"review:{review_id}:timeline")
        try:
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            timeout = 300  # 5 minute max stream
            elapsed = 0
            while elapsed < timeout:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
                await asyncio.sleep(0.1)
                elapsed += 0.1
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(f"review:{review_id}:timeline")
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
