"""
Idempotency-Key header enforcement via Valkey.

Flow:
  1. Client sends header  Idempotency-Key: <uuid>
  2. Middleware checks Valkey for key idempotency:<key>
  3a. Exists   → return stored JSON response (HTTP status + body)
  3b. Not found → acquire lock, process request, store result, return it

TTL: 24 hours (configurable)
"""

import asyncio
import json
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.redis.client import get_redis_client

logger = logging.getLogger(__name__)

IDEMPOTENCY_TTL = 60 * 60 * 24  # 24 hours in seconds
IDEMPOTENCY_METHODS = {"POST", "PATCH"}
LOCK_TTL = 30  # seconds – lock while processing the request
LOCK_POLL_S = 0.25  # poll interval when waiting for a lock
LOCK_WAIT_TIMEOUT = 10  # max seconds to wait for a locked request


def _redis_key(idempotency_key: str) -> str:
    return f"idempotency:{idempotency_key}"


def _lock_key(idempotency_key: str) -> str:
    return f"idempotency:{idempotency_key}:lock"


def _parse_cached(raw: str) -> dict | None:
    """Parse and validate a cached idempotency entry. Returns None on failure."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or "body" not in data or "status_code" not in data:
        return None
    return data


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Intercepts POST/PATCH requests carrying an Idempotency-Key header."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in IDEMPOTENCY_METHODS:
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        rkey = _redis_key(idempotency_key)
        lkey = _lock_key(idempotency_key)

        try:
            redis = await get_redis_client()
            cached = await redis.get(rkey)
        except Exception:
            logger.warning("Idempotency: Redis unavailable – falling through", exc_info=True)
            return await call_next(request)

        # ── Cached response exists → replay ──
        if cached:
            data = _parse_cached(cached)
            if data is None:
                logger.warning("Idempotency: corrupt cache for key=%s – deleting", rkey)
                try:
                    await redis.delete(rkey)
                except Exception:
                    pass
                return await call_next(request)

            return Response(
                content=data["body"],
                status_code=data["status_code"],
                media_type="application/json",
                headers={"X-Idempotent-Replay": "true"},
            )

        # ── No cache: acquire per-key lock before processing ──
        try:
            lock_acquired = await redis.set(lkey, "1", nx=True, ex=LOCK_TTL)
        except Exception:
            logger.warning("Idempotency: Redis lock failed – falling through", exc_info=True)
            lock_acquired = False

        if not lock_acquired:
            # Another request is processing this key — poll for the result
            elapsed = 0.0
            while elapsed < LOCK_WAIT_TIMEOUT:
                await asyncio.sleep(LOCK_POLL_S)
                elapsed += LOCK_POLL_S
                try:
                    cached = await redis.get(rkey)
                except Exception:
                    break
                if cached:
                    data = _parse_cached(cached)
                    if data is None:
                        break
                    return Response(
                        content=data["body"],
                        status_code=data["status_code"],
                        media_type="application/json",
                        headers={"X-Idempotent-Replay": "true"},
                    )
            # Timed out waiting — fall through to normal processing
            return await call_next(request)

        # ── Process the real request under the lock ──
        try:
            response: Response = await call_next(request)

            # Only cache successful mutations
            if response.status_code in (200, 201):
                body_bytes = b""
                async for chunk in response.body_iterator:
                    body_bytes += chunk
                body_str = body_bytes.decode("utf-8")

                try:
                    await redis.set(
                        rkey,
                        json.dumps({"status_code": response.status_code, "body": body_str}),
                        ex=IDEMPOTENCY_TTL,
                    )
                except Exception:
                    logger.warning("Idempotency: failed to cache response", exc_info=True)

                # Preserve original downstream headers (Set-Cookie, etc.)
                resp_headers = dict(response.headers) if response.headers else {}
                resp_headers.pop("content-length", None)  # will be recalculated
                resp_headers.pop("content-encoding", None)
                # Remove content-type case-insensitively — Response(media_type=...) sets it
                for k in [k for k in resp_headers if k.lower() == "content-type"]:
                    resp_headers.pop(k)

                return Response(
                    content=body_str,
                    status_code=response.status_code,
                    media_type=response.media_type or "application/json",
                    headers=resp_headers,
                )

            return response
        finally:
            try:
                await redis.delete(lkey)
            except Exception:
                pass
