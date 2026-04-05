import re
import time
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.database import async_session
from app.models.access_log import AccessLog

logger = logging.getLogger(__name__)

# Patterns for PII in URL paths (UUIDs, numeric IDs, emails)
_ID_PATTERN = re.compile(r"/\d+")
_UUID_PATTERN = re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"/[^/]+@[^/]+")


def sanitize_endpoint_url(path: str) -> str:
    """Strip PII from URL paths: numeric IDs → /:id, UUIDs → /:uuid, emails → /:email."""
    path = _UUID_PATTERN.sub("/:uuid", path)
    path = _EMAIL_PATTERN.sub("/:email", path)
    path = _ID_PATTERN.sub("/:id", path)
    # strip query strings entirely
    return path.split("?")[0]


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Logs every incoming request to the access_logs table."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        # Best-effort: extract user_id from request state (set by auth dep)
        user_id = None
        try:
            user_id = request.state.user_id
        except AttributeError:
            pass

        try:
            async with async_session() as session:
                session.add(AccessLog(
                    user_id=user_id,
                    endpoint=sanitize_endpoint_url(str(request.url.path)),
                    method=request.method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                ))
                await session.commit()
        except Exception:
            logger.warning("Failed to write access log", exc_info=True)

        return response
