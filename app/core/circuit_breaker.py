"""
Circuit Breaker wrappers for external service calls.

Uses pybreaker to protect against cascading failures when Kafka or Redis is
temporarily unavailable. Each external service gets its own breaker.

States:
  CLOSED   -> normal operation, failures are counted
  OPEN     -> short-circuited, raises CircuitBreakerError immediately
  HALF-OPEN-> allows a trial call to determine recovery

Config:
  fail_max      - consecutive failures before opening   (default: 5)
  reset_timeout - seconds in OPEN before transitioning to HALF-OPEN (default: 30)

Note on pybreaker 1.2.0:
  call_async() has a bug: it references 'gen' (a Tornado module) which is
  never imported, causing NameError with native async/await. Use
  call_breaker_async() from this module instead.
"""

import logging
from functools import wraps
from typing import Any, Callable

import pybreaker

logger = logging.getLogger(__name__)


class _BreakerListener(pybreaker.CircuitBreakerListener):
    """Log circuit breaker state transitions."""

    def state_change(self, cb: pybreaker.CircuitBreaker, old_state, new_state):
        logger.warning(
            "Circuit breaker '%s': %s -> %s",
            cb.name, old_state.name, new_state.name,
        )

    def failure(self, cb: pybreaker.CircuitBreaker, exc: Exception):
        logger.debug("Circuit breaker '%s' recorded failure: %s", cb.name, exc)

    def success(self, cb: pybreaker.CircuitBreaker):
        logger.debug("Circuit breaker '%s' recorded success", cb.name)


_listener = _BreakerListener()

# ── Pre-configured breakers for each external dependency ──

kafka_breaker = pybreaker.CircuitBreaker(
    name="kafka",
    fail_max=5,
    reset_timeout=30,
    listeners=[_listener],
    exclude=[KeyboardInterrupt, SystemExit],
)

redis_breaker = pybreaker.CircuitBreaker(
    name="redis",
    fail_max=5,
    reset_timeout=15,
    listeners=[_listener],
    exclude=[KeyboardInterrupt, SystemExit],
)

database_breaker = pybreaker.CircuitBreaker(
    name="database",
    fail_max=5,
    reset_timeout=30,
    listeners=[_listener],
    exclude=[KeyboardInterrupt, SystemExit],
)


async def call_breaker_async(
    breaker: pybreaker.CircuitBreaker,
    coro_func: Callable,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Async-safe circuit breaker wrapper that works with pybreaker 1.2.0.

    pybreaker's built-in call_async() was written for Tornado's old
    @gen.coroutine style and references an undefined 'gen' name when used
    with native async/await, raising NameError at runtime.

    This helper uses pybreaker's public calling() context manager which:
      - Raises CircuitBreakerError immediately when the breaker is OPEN
      - Records success/failure on exit to update the breaker state
    """
    import asyncio
    try:
        result = await coro_func(*args, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception:
        with breaker.calling():
            raise
    else:
        with breaker.calling():
            return result


def with_breaker(breaker: pybreaker.CircuitBreaker):
    """Decorator for async functions - wraps them with a circuit breaker."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await call_breaker_async(breaker, func, *args, **kwargs)
        return wrapper

    return decorator
