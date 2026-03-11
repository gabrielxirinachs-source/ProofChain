"""
app/core/config.py

Why pydantic-settings?
  - Reads from environment variables AND .env files automatically
  - Type-validates every config value at startup (fail fast)
  - Single source of truth for all configuration
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────
    APP_NAME: str = "ProofChain Fact-Check"
    APP_VERSION: str = "0.1.0"
    ENV: str = "development"
    DEBUG: bool = True

    # ── Database ──────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://proofchain:proofchain@localhost:5432/proofchain"

    # ── Redis ─────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_TTL_SECONDS: int = 3600  # 1 hour default cache

    # ── AI ────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"  # Affordable for dev; swap to gpt-4o for prod

    # ── Wikidata ──────────────────────────────────────────
    WIKIDATA_SPARQL_URL: str = "https://query.wikidata.org/sparql"
    WIKIDATA_USER_AGENT: str = "ProofChain/0.1 (fact-checking research project)"

    # ── Web Retrieval ─────────────────────────────────────
    MAX_WEB_SOURCES: int = 5       # Max pages to fetch per claim
    WEB_FETCH_TIMEOUT_SEC: int = 15

    # ── Agent Loop ────────────────────────────────────────
    MAX_AGENT_ITERATIONS: int = 10  # Safety ceiling on the MDP loop

    # Tells pydantic-settings to also load from a .env file
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    """
    Cached singleton — settings are read once at startup.
    Use: from app.core.config import get_settings; s = get_settings()
    """
    return Settings()