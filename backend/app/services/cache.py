"""
app/services/cache.py

Redis caching service for verification results.

Why cache /verify results?
  - A full fact-check run takes 10-30 seconds (LLM calls + web fetches)
  - If someone asks the same claim twice, we should return instantly
  - Redis stores results in memory — microsecond reads
  - TTL (time-to-live) ensures stale verdicts expire after 1 hour

Cache key design:
  We hash the claim text to create a consistent cache key.
  "The Eiffel Tower is 330m tall" and "the eiffel tower is 330m tall"
  should hit the same cache entry — so we lowercase + strip before hashing.
"""
import json
import hashlib
import redis.asyncio as aioredis
from typing import Any

from app.core.config import get_settings

settings = get_settings()

# Module-level client — created once, reused across requests
_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """
    Get or create the Redis client.
    Uses a module-level singleton to reuse the connection pool.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


def make_cache_key(claim_text: str) -> str:
    """
    Create a deterministic cache key from a claim.

    We normalize (lowercase + strip) before hashing so
    minor variations in capitalization hit the same cache entry.

    Args:
        claim_text: The raw claim string

    Returns:
        Cache key string, e.g. "proofchain:verify:a3f8b2c1..."
    """
    normalized = claim_text.lower().strip()
    claim_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"proofchain:verify:{claim_hash}"


async def get_cached_result(claim_text: str) -> dict | None:
    """
    Look up a cached verification result.

    Args:
        claim_text: The claim to look up

    Returns:
        Cached result dict, or None if not cached
    """
    try:
        redis = await get_redis()
        key = make_cache_key(claim_text)
        cached = await redis.get(key)

        if cached:
            return json.loads(cached)
        return None

    except Exception as e:
        # Never let cache failures crash the API
        # If Redis is down, just proceed without caching
        print(f"[cache] Redis get failed: {e}")
        return None


async def set_cached_result(
    claim_text: str,
    result: dict,
    ttl_seconds: int | None = None,
) -> bool:
    """
    Store a verification result in cache.

    Args:
        claim_text:  The claim that was verified
        result:      The verification result dict to cache
        ttl_seconds: How long to cache (defaults to settings.CACHE_TTL_SECONDS)

    Returns:
        True if cached successfully, False if cache failed
    """
    try:
        redis = await get_redis()
        key = make_cache_key(claim_text)
        ttl = ttl_seconds or settings.CACHE_TTL_SECONDS

        await redis.setex(
            key,
            ttl,
            json.dumps(result),
        )
        return True

    except Exception as e:
        print(f"[cache] Redis set failed: {e}")
        return False


async def invalidate_cache(claim_text: str) -> bool:
    """
    Remove a cached result (useful if evidence was updated).

    Args:
        claim_text: The claim whose cache to invalidate

    Returns:
        True if deleted, False if not found or failed
    """
    try:
        redis = await get_redis()
        key = make_cache_key(claim_text)
        deleted = await redis.delete(key)
        return deleted > 0

    except Exception as e:
        print(f"[cache] Redis delete failed: {e}")
        return False


async def check_redis_health() -> str:
    """
    Check if Redis is reachable.
    Used by the /health/ready endpoint.

    Returns:
        "ok" if Redis responds, "error: <msg>" otherwise
    """
    try:
        redis = await get_redis()
        await redis.ping()
        return "ok"
    except Exception as e:
        return f"error: {e}"