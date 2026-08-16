from fastapi import APIRouter

from app.api.v1 import webhooks, repositories, reviews, findings, stats

api_router = APIRouter()

api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(repositories.router, prefix="/repositories", tags=["repositories"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(findings.router, prefix="/findings", tags=["findings"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
