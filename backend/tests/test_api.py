"""
API endpoint tests.
"""
import pytest
from sqlalchemy import select

from app.api.v1.webhooks import _handle_installation, _handle_installation_repositories
from app.models.repository import Repository


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_list_reviews_empty(client):
    resp = await client.get("/api/v1/reviews/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_repositories_empty(client):
    resp = await client.get("/api/v1/repositories/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_stats_dashboard(client):
    resp = await client.get("/api/v1/stats/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_reviews" in data
    assert "findings_by_severity" in data


@pytest.mark.asyncio
async def test_review_not_found(client):
    resp = await client.get("/api/v1/reviews/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_finding_not_found(client):
    resp = await client.get("/api/v1/findings/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_installation_webhook_records_repositories(db):
    await _handle_installation(
        db,
        {
            "installation": {
                "id": 123,
                "account": {"login": "octo", "type": "User"},
            },
            "repositories": [
                {
                    "id": 456,
                    "full_name": "octo/example",
                    "name": "example",
                    "private": True,
                }
            ],
        },
    )

    result = await db.execute(select(Repository).where(Repository.github_id == 456))
    repo = result.scalar_one()
    assert repo.full_name == "octo/example"
    assert repo.owner == "octo"
    assert repo.installation_id == 123
    assert repo.private is True


@pytest.mark.asyncio
async def test_installation_repositories_added_and_removed_updates_repositories(db):
    await _handle_installation_repositories(
        db,
        {
            "installation": {"id": 999},
            "repositories_added": [
                {
                    "id": 777,
                    "full_name": "acme/web",
                    "name": "web",
                    "private": False,
                }
            ],
            "repositories_removed": [],
        },
    )

    result = await db.execute(select(Repository).where(Repository.github_id == 777))
    repo = result.scalar_one()
    assert repo.enabled is True
    assert repo.installation_id == 999

    await _handle_installation_repositories(
        db,
        {
            "installation": {"id": 999},
            "repositories_added": [],
            "repositories_removed": [{"id": 777}],
        },
    )

    assert repo.enabled is False
