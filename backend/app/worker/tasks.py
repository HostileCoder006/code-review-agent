"""
Background job tasks using arq (Redis-backed job queue).
"""
import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.review import Review
from app.orchestrator.review_orchestrator import ReviewOrchestrator

log = structlog.get_logger(__name__)


async def run_review(ctx, review_id: str, installation_id: int):
    """arq job: run the full review pipeline."""
    log.info("job_started", review_id=review_id)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Review)
            .options(selectinload(Review.repository))
            .where(Review.id == review_id)
        )
        review = result.scalar_one_or_none()
        if not review:
            log.error("review_not_found", review_id=review_id)
            return

        orchestrator = ReviewOrchestrator(db, installation_id)
        await orchestrator.run(review)
        await db.commit()

    log.info("job_completed", review_id=review_id)


async def enqueue_review(review_id: str, installation_id: int):
    """Enqueue a review job via arq."""
    from arq import create_pool
    from app.core.config import settings

    redis = await create_pool({"host": settings.REDIS_URL})
    await redis.enqueue_job("run_review", review_id=review_id, installation_id=installation_id)
    await redis.close()
    log.info("review_enqueued", review_id=review_id)


class WorkerSettings:
    redis_settings_from_url = None
    functions = [run_review]
    max_jobs = 5
    job_timeout = 600  # 10 minutes max per job

    @classmethod
    def get_redis_settings(cls):
        from arq.connections import RedisSettings
        from app.core.config import settings
        import re
        # Parse redis URL
        m = re.match(r"redis://([^:/]+):?(\d+)?/(\d+)?", settings.REDIS_URL)
        host = m.group(1) if m else "localhost"
        port = int(m.group(2)) if m and m.group(2) else 6379
        db = int(m.group(3)) if m and m.group(3) else 0
        return RedisSettings(host=host, port=port, database=db)
