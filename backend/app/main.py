"""
app/main.py — FastAPI application entrypoint

Key concepts here:
  - Lifespan: replaces old @app.on_event("startup"). It's a context manager
    that runs setup BEFORE the app accepts requests and teardown AFTER.
  - APIRouter: keeps routes in separate files; main.py just assembles them.
  - CORS: needed later when the React frontend talks to this API.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api import health  # We'll add more routers as phases progress

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Everything before `yield` runs at startup.
    Everything after `yield` runs at shutdown.
    """
    print(f"🔗 Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENV}]")
    # Phase 2: database connection pool will be initialized here
    # Phase 7: OpenTelemetry tracer will be initialized here
    yield
    print("🔗 ProofChain shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-agent fact-checking engine with auditable evidence graphs.",
    docs_url="/docs",        # Swagger UI at /docs
    redoc_url="/redoc",      # ReDoc UI at /redoc
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allows the React frontend (on a different port) to call this API.
# In production, replace "*" with your actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENV == "development" else ["https://yourapp.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
# Each phase will add a new router here, e.g.:
#   from app.api import verify
#   app.include_router(verify.router, prefix="/api/v1", tags=["Verification"])
app.include_router(health.router, tags=["Health"])