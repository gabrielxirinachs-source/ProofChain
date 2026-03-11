"""
app/api/health.py

A health check endpoint is standard practice for any production service.
Load balancers and container orchestrators (like Fly.io, Kubernetes) ping
this to know if your service is alive and ready to receive traffic.

Two patterns:
  - /health/live  → "Is the process running?" (liveness)
  - /health/ready → "Is it ready to serve traffic?" (readiness — checks DB, Redis)
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.config import get_settings

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
    """Basic liveness — just confirms the process is up."""
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
    Phase 2: will add real DB + Redis ping checks here.
    """
    checks = {
        "database": "not_configured",  # TODO: Phase 2
        "redis": "not_configured",      # TODO: Phase 2
    }

    all_ok = all(v in ("ok", "not_configured") for v in checks.values())

    return ReadinessResponse(
        status="ready" if all_ok else "degraded",
        checks=checks,
    )