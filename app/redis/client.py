"""
Async Redis/Valkey client – connects to Aiven with TLS (rediss://).

Usage:
    from app.redis.client import get_redis

    async def my_dep(redis=Depends(get_redis)):
        await redis.set("key", "val")
"""

import asyncio
import logging
import os
import ssl
from typing import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Module-level pool – created once, reused across requests
_redis_pool: Redis | None = None
_redis_lock = asyncio.Lock()


def _build_client() -> Redis:
    """Construct an async Redis client from REDIS_URL.

    Aiven Valkey URLs start with rediss:// which enables TLS automatically.
    """
    kwargs = {
        "decode_responses": True,
        "socket_timeout": 5,
        "socket_connect_timeout": 5,
        "retry_on_timeout": True,
    }
    
    if settings.REDIS_URL.startswith("rediss://"):
        ca_file = getattr(settings, "REDIS_SSL_CA_CERTS", "ca.pem")
        if ca_file and os.path.exists(ca_file):
            logger.info("Valkey TLS: using CA cert from %s", ca_file)
            kwargs["ssl_ca_certs"] = ca_file
            
    return aioredis.from_url(settings.REDIS_URL, **kwargs)


async def get_redis_client() -> Redis:
    """Return the shared Redis client (lazy-initialised, concurrency-safe)."""
    global _redis_pool
    if _redis_pool is not None:
        return _redis_pool
    async with _redis_lock:
        # Double-check after acquiring lock
        if _redis_pool is None:
            _redis_pool = _build_client()
    return _redis_pool


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency – yields the shared Redis client."""
    client = await get_redis_client()
    yield client


async def close_redis() -> None:
    """Close the Redis connection pool (call on app shutdown)."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
