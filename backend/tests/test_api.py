"""
API endpoint tests.
"""
import pytest


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
