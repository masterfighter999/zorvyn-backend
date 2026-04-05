"""
Cache-aside helpers for the dashboard APIs.

Keys:
  dashboard:summary:{user_id}       TTL 5 min
  dashboard:trends:{user_id}:{months}  TTL 5 min
  dashboard:categories:{type}       TTL 5 min
  dashboard:recent:{limit}          TTL 1 min

Invalidation:
  On any record mutation call invalidate_dashboard_cache().
"""

import json
import logging
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

SUMMARY_TTL = 60 * 5      # 5 minutes
TRENDS_TTL = 60 * 1       # 1 minute – keep fresh between toggle clicks
CATEGORIES_TTL = 60 * 5
RECENT_TTL = 60 * 1       # 1 minute

# Tag used for round-tripping Decimal through JSON
_DECIMAL_TAG = "__decimal__"


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return {_DECIMAL_TAG: str(obj)}
        return super().default(obj)


def _decode_decimals(obj: Any) -> Any:
    """Recursively restore tagged Decimal values from parsed JSON."""
    if isinstance(obj, dict):
        if _DECIMAL_TAG in obj and len(obj) == 1:
            return Decimal(obj[_DECIMAL_TAG])
        return {k: _decode_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_decimals(i) for i in obj]
    return obj


async def get_cached(redis: Redis, key: str) -> Any | None:
    try:
        raw = await redis.get(key)
        if raw:
            return _decode_decimals(json.loads(raw))
    except Exception:
        logger.warning("Cache get failed for %s", key, exc_info=True)
    return None


async def set_cached(redis: Redis, key: str, value: Any, ttl: int) -> None:
    try:
        await redis.set(key, json.dumps(value, cls=DecimalEncoder), ex=ttl)
    except Exception:
        logger.warning("Cache set failed for %s", key, exc_info=True)


async def invalidate_dashboard_cache(redis: Redis) -> None:
    """Delete all dashboard:* keys on record mutations using non-blocking SCAN."""
    try:
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match="dashboard:*", count=200)
            if keys:
                await redis.unlink(*keys)
            if cursor == 0:
                break
    except Exception:
        logger.warning("Cache invalidation failed", exc_info=True)


# ── Per-endpoint cache key helpers ──

def summary_key(user_id: int) -> str:
    return f"dashboard:summary:{user_id}"


def trends_key(user_id: int, identifier: str) -> str:
    return f"dashboard:trends:{user_id}:{identifier}"


def categories_key(record_type: str | None) -> str:
    return f"dashboard:categories:{record_type or 'all'}"


def recent_key(limit: int) -> str:
    return f"dashboard:recent:{limit}"
