"""Admin-only endpoints for system health and DLQ monitoring."""

from fastapi import APIRouter, Depends

from app.core.security import require_role
from app.kafka.dlq_consumer import get_dlq_stats
from app.core.circuit_breaker import kafka_breaker, redis_breaker, database_breaker

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/dlq", dependencies=[Depends(require_role("admin"))])
async def dlq_status():
    """Return DLQ event count and recent failed events."""
    return get_dlq_stats()


@router.get("/circuit-breakers", dependencies=[Depends(require_role("admin"))])
async def circuit_breaker_status():
    """Return the current state of all circuit breakers."""
    return {
        "kafka": {
            "state": kafka_breaker.current_state,
            "fail_counter": kafka_breaker.fail_counter,
            "fail_max": kafka_breaker.fail_max,
            "reset_timeout": kafka_breaker.reset_timeout,
        },
        "redis": {
            "state": redis_breaker.current_state,
            "fail_counter": redis_breaker.fail_counter,
            "fail_max": redis_breaker.fail_max,
            "reset_timeout": redis_breaker.reset_timeout,
        },
        "database": {
            "state": database_breaker.current_state,
            "fail_counter": database_breaker.fail_counter,
            "fail_max": database_breaker.fail_max,
            "reset_timeout": database_breaker.reset_timeout,
        },
    }
