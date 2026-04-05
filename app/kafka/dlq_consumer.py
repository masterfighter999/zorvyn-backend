"""
DLQ Consumer – monitors and optionally reprocesses dead-letter events.

Subscribes to finance.dlq and logs every failed event for observability.
Exposes a FastAPI router at /admin/dlq for inspecting DLQ status.
"""

import asyncio
import json
import logging
from typing import Any
from collections import deque

from aiokafka import AIOKafkaConsumer

from app.core.config import get_settings
from app.kafka.producer import TOPIC_DLQ
from app.kafka.ssl import build_ssl_context

logger = logging.getLogger(__name__)

settings = get_settings()

# In-memory ring buffer of recent DLQ events (latest 100)
_dlq_events: deque[dict[str, Any]] = deque(maxlen=100)
_dlq_count: int = 0


async def _process_dlq_event(event: dict[str, Any]) -> None:
    """Handle a DLQ event – log and store in ring buffer."""
    global _dlq_count
    _dlq_count += 1
    _dlq_events.append(event)
    logger.error(
        "DLQ EVENT #%d: original_topic=%s event_type=%s aggregate=%s:%s retries=%s reason=%s",
        _dlq_count,
        event.get("payload", {}).get("original_topic"),
        event.get("event_type"),
        event.get("aggregate_type"),
        event.get("aggregate_id"),
        event.get("payload", {}).get("retry_count"),
        event.get("payload", {}).get("failure_reason"),
    )


def get_dlq_stats() -> dict[str, Any]:
    """Return current DLQ statistics and recent events."""
    return {
        "total_dlq_events": _dlq_count,
        "recent_events_count": len(_dlq_events),
        "recent_events": list(_dlq_events),
    }


async def run_dlq_consumer() -> None:
    """Entry-point: start the DLQ consumer loop."""
    ssl_context = build_ssl_context()

    consumer = AIOKafkaConsumer(
        TOPIC_DLQ,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="zorvyn-dlq-monitor",
        security_protocol="SSL" if ssl_context else "PLAINTEXT",
        ssl_context=ssl_context,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )

    await consumer.start()
    logger.info("DLQ consumer started on topic=%s", TOPIC_DLQ)

    try:
        async for msg in consumer:
            await _process_dlq_event(msg.value)
    except asyncio.CancelledError:
        logger.info("DLQ consumer cancelled")
    except Exception:
        logger.exception("DLQ consumer error")
    finally:
        await consumer.stop()
        logger.info("DLQ consumer stopped")
