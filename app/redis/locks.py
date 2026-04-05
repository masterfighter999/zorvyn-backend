"""
Distributed lock helpers using Valkey SET NX PX.

Usage:
    async with acquire_lock(redis, "record", record_id, ttl_ms=5000):
        # critical section
        ...

Raises LockNotAcquiredError if the lock cannot be obtained within `timeout_ms`.
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

LOCK_DEFAULT_TTL_MS = 5_000    # 5 seconds
LOCK_RETRY_MS = 50             # poll interval


class LockNotAcquiredError(RuntimeError):
    pass


def _lock_key(resource: str, resource_id: int | str) -> str:
    return f"lock:{resource}:{resource_id}"


@asynccontextmanager
async def acquire_lock(
    redis: Redis,
    resource: str,
    resource_id: int | str,
    ttl_ms: int = LOCK_DEFAULT_TTL_MS,
    timeout_ms: int = 3_000,
) -> AsyncGenerator[None, None]:
    """Acquire a distributed lock; release it when the context exits."""
    key = _lock_key(resource, resource_id)
    token = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000

    acquired = False
    while loop.time() < deadline:
        ok = await redis.set(key, token, px=ttl_ms, nx=True)
        if ok:
            acquired = True
            break
        await asyncio.sleep(LOCK_RETRY_MS / 1000)

    if not acquired:
        raise LockNotAcquiredError(f"Could not acquire lock for {key}")

    try:
        yield
    finally:
        # Release only if the token still matches (guards against TTL expiry)
        lua_script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
        """
        try:
            await redis.eval(lua_script, 1, key, token)
        except Exception:
            logger.warning("Lock release failed for %s", key, exc_info=True)
