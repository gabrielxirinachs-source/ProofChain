"""
app/main.py — FastAPI application entrypoint
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api import health
from app.api import verify

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🔗 Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENV}]")
    yield
    print("🔗 ProofChain shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-agent fact-checking engine with auditable evidence graphs.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for now
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────
app.include_router(health.router, tags=["Health"])
app.include_router(verify.router, tags=["Verification"])

# ── Telemetry (must happen after app creation, before first request) ──
if settings.ENV != "test":
    try:
        from app.core.telemetry import setup_telemetry
        setup_telemetry(app)
    except Exception as e:
        print(f"[telemetry] Failed to initialize: {e}")