"""
tests/test_health.py

Why write tests from day 1?
  - Forces you to think about what "correct" looks like before you code
  - Gives you a safety net as the codebase grows
  - GitHub CI will run these automatically (Phase 7)

pytest-asyncio lets you write async test functions with `async def`.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_liveness():
    """Health check should always return 200 with status=ok."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness():
    """Readiness should return 200 even when deps aren't configured yet."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ready", "degraded")
    assert "checks" in data