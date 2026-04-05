"""
Aiven Kafka async producer using aiokafka with SSL/TLS.

Topics:
  finance.records   – record lifecycle events
  finance.audit     – audit trail events
  finance.analytics – analytics events
  finance.dlq       – dead letter queue

Aiven requires SSL certs placed in project root (downloaded from Aiven console):
  ca.pem / service.cert / service.key
"""

import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer
import pybreaker

from app.core.config import get_settings
from app.core.circuit_breaker import kafka_breaker, call_breaker_async
from app.kafka.ssl import build_ssl_context

logger = logging.getLogger(__name__)

# ── Kafka topic names ──
TOPIC_RECORDS = "finance.records"
TOPIC_AUDIT = "finance.audit"
TOPIC_ANALYTICS = "finance.analytics"
TOPIC_DLQ = "finance.dlq"

settings = get_settings()
_producer: AIOKafkaProducer | None = None
_producer_lock = asyncio.Lock()


async def get_producer() -> AIOKafkaProducer:
    """Return the shared Kafka producer (lazy-started, thread-safe)."""
    global _producer
    if _producer is not None:
        return _producer
    async with _producer_lock:
        # Double-check after acquiring lock
        if _producer is not None:
            return _producer
        ssl_context = build_ssl_context()
        new_producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            security_protocol="SSL" if ssl_context else "PLAINTEXT",
            ssl_context=ssl_context,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: str(k).encode("utf-8") if k else None,
            acks="all",
            enable_idempotence=True,
            compression_type="gzip",
            retry_backoff_ms=500,
        )
        await new_producer.start()
        _producer = new_producer
        logger.info("Kafka producer started (brokers=%s)", settings.KAFKA_BOOTSTRAP_SERVERS)
    return _producer


async def close_producer() -> None:
    """Gracefully stop the Kafka producer."""
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None
        logger.info("Kafka producer stopped")


async def send_event(
    topic: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: int,
    payload: dict[str, Any],
    key: str | None = None,
) -> None:
    """Publish a single structured event to a Kafka topic (circuit-breaker protected)."""
    message = {
        "event_type": event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "payload": payload,
    }

    async def _send():
        producer = await get_producer()
        await producer.send_and_wait(topic, value=message, key=key or str(aggregate_id))

    try:
        # call_breaker_async drives pybreaker's state machine natively in async
        # without the Tornado-era gen.Return bug in pybreaker 1.2.0's call_async.
        await call_breaker_async(kafka_breaker, _send)
    except pybreaker.CircuitBreakerError:
        logger.error(
            "Kafka circuit breaker OPEN: topic=%s event=%s id=%s",
            topic, event_type, aggregate_id,
        )
        raise
    except Exception as exc:
        logger.error("Kafka send failed: topic=%s event=%s error=%s", topic, event_type, exc, exc_info=True)
        raise
    else:
        logger.debug("Kafka event sent: topic=%s event=%s id=%s", topic, event_type, aggregate_id)
