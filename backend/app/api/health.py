"""
app/api/health.py

Health check endpoints — used by load balancers and CI to verify
the service is alive and all dependencies are reachable.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.config import get_settings
from app.services.cache import check_redis_health

router = APIRouter()
settings = get_settings()


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    timestamp: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health/live", response_model=HealthResponse)
async def liveness():
    """Basic liveness — confirms the process is up."""
    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENV,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness():
    """
    Readiness — checks all dependencies.
    Returns degraded if Redis is unreachable (DB check added in Phase 7).
    """
    redis_status = await check_redis_health()

    checks = {
        "database": "not_configured",
        "redis": redis_status,
    }

    all_ok = all(v in ("ok", "not_configured") for v in checks.values())

    return ReadinessResponse(
        status="ready" if all_ok else "degraded",
        checks=checks,
    )