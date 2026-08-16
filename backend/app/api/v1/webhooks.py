"""
GitHub webhook handler. Receives PR events and enqueues review jobs.
"""
import json

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.core.database import get_db
from app.github.webhook import verify_signature
from app.models.repository import Repository
from app.models.review import Review, ReviewStatus
from app.models.installation import Installation
from app.worker.tasks import enqueue_review

router = APIRouter()
log = structlog.get_logger(__name__)


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    body = await verify_signature(request)
    event = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body)

    log.info("webhook_received", event=event, action=payload.get("action"))

    if event == "installation":
        await _handle_installation(db, payload)
        return {"status": "ok"}

    if event == "pull_request":
        action = payload.get("action", "")
        if action in ("opened", "synchronize", "reopened"):
            await _handle_pull_request(db, background_tasks, payload)
        return {"status": "ok"}

    return {"status": "ignored"}


async def _handle_installation(db: AsyncSession, payload: dict):
    installation_data = payload.get("installation", {})
    installation_id = installation_data.get("id")
    if not installation_id:
        return

    result = await db.execute(
        select(Installation).where(Installation.installation_id == installation_id)
    )
    installation = result.scalar_one_or_none()

    if not installation:
        installation = Installation(
            installation_id=installation_id,
            account_login=installation_data.get("account", {}).get("login", ""),
            account_type=installation_data.get("account", {}).get("type", "User"),
        )
        db.add(installation)
        await db.flush()


async def _handle_pull_request(db: AsyncSession, background_tasks: BackgroundTasks, payload: dict):
    pr = payload["pull_request"]
    repo_data = payload["repository"]
    installation_id = payload.get("installation", {}).get("id")

    # Upsert repository
    result = await db.execute(
        select(Repository).where(Repository.github_id == repo_data["id"])
    )
    repository = result.scalar_one_or_none()

    if not repository:
        repository = Repository(
            github_id=repo_data["id"],
            full_name=repo_data["full_name"],
            owner=repo_data["owner"]["login"],
            name=repo_data["name"],
            default_branch=repo_data.get("default_branch", "main"),
            language=repo_data.get("language"),
            private=repo_data.get("private", False),
            installation_id=installation_id,
        )
        db.add(repository)
        await db.flush()
    elif installation_id:
        repository.installation_id = installation_id
        await db.flush()

    if not repository.enabled:
        log.info("repository_disabled", repo=repo_data["full_name"])
        return

    # Check for duplicate review
    result = await db.execute(
        select(Review).where(
            Review.repository_id == repository.id,
            Review.pr_number == pr["number"],
            Review.head_sha == pr["head"]["sha"],
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        log.info("duplicate_review_skipped", pr=pr["number"])
        return

    # Create review record
    review = Review(
        repository_id=repository.id,
        pr_number=pr["number"],
        pr_title=pr["title"][:1024],
        pr_author=pr["user"]["login"],
        pr_url=pr["html_url"],
        base_sha=pr["base"]["sha"],
        head_sha=pr["head"]["sha"],
        status=ReviewStatus.pending,
    )
    db.add(review)
    await db.flush()

    log.info("review_created", review_id=str(review.id), pr=pr["number"])

    # Enqueue background job
    background_tasks.add_task(
        enqueue_review,
        review_id=str(review.id),
        installation_id=installation_id,
    )
