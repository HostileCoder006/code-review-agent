"""
Background job tasks using arq (Redis-backed job queue).
"""
import structlog
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
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


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.REDIS_URL)


async def enqueue_review(review_id: str, installation_id: int):
    """Enqueue a review job via arq."""
    from arq import create_pool

    redis = await create_pool(_redis_settings())
    await redis.enqueue_job("run_review", review_id=review_id, installation_id=installation_id)
    await redis.close()
    log.info("review_enqueued", review_id=review_id)


class WorkerSettings:
    functions = [run_review]
    max_jobs = 5
    job_timeout = 600  # 10 minutes max per job
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
