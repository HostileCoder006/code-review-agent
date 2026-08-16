from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import structlog

from app.core.database import get_db
from app.models.repository import Repository
from app.schemas.repository import RepositoryOut

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/", response_model=list[RepositoryOut])
async def list_repositories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Repository).order_by(Repository.full_name))
    return result.scalars().all()


@router.get("/{repo_id}", response_model=RepositoryOut)
async def get_repository(repo_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Repository).where(Repository.id == repo_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.patch("/{repo_id}/toggle")
async def toggle_repository(repo_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    repo.enabled = not repo.enabled
    await db.flush()
    return {"enabled": repo.enabled}
