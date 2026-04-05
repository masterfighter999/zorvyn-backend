"""
Aiven Kafka async consumer for audit and analytics topics.

Subscribes to:
  finance.audit     – logs audit events to activity_logs table
  finance.analytics – placeholder for downstream analytics processing

If processing fails after MAX_RETRIES, the event is routed to finance.dlq.
"""

import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from app.core.config import get_settings
from app.kafka.dlq import send_to_dlq, DLQSendError
from app.kafka.producer import TOPIC_AUDIT, TOPIC_ANALYTICS
from app.kafka.ssl import build_ssl_context

logger = logging.getLogger(__name__)

settings = get_settings()

MAX_RETRIES = 3
RETRY_BACKOFF_S = 2.0
CONSUMER_GROUP = "zorvyn-backend"


async def _process_audit_event(event: dict[str, Any]) -> None:
    """Handle an audit event (logging only in this phase)."""
    logger.info(
        "AUDIT EVENT: type=%s aggregate=%s id=%s",
        event.get("event_type"),
        event.get("aggregate_type"),
        event.get("aggregate_id"),
    )


async def _process_event(topic: str, event: dict[str, Any]) -> None:
    if topic == TOPIC_AUDIT:
        await _process_audit_event(event)
    elif topic == TOPIC_ANALYTICS:
        logger.debug("ANALYTICS EVENT received: %s", event.get("event_type"))


async def run_consumer(topics: list[str] | None = None) -> None:
    """Entry-point: start the Kafka consumer loop."""
    topics = topics or [TOPIC_AUDIT, TOPIC_ANALYTICS]
    ssl_context = build_ssl_context()

    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=CONSUMER_GROUP,
        security_protocol="SSL" if ssl_context else "PLAINTEXT",
        ssl_context=ssl_context,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,   # manual commit after processing
    )

    await consumer.start()
    logger.info("Kafka consumer started, topics=%s", topics)

    try:
        async for msg in consumer:
            event = msg.value
            retry_count = 0
            success = False

            while retry_count < MAX_RETRIES:
                try:
                    await _process_event(msg.topic, event)
                    await consumer.commit()
                    success = True
                    break
                except Exception as exc:
                    retry_count += 1
                    logger.warning(
                        "Consumer error (attempt %d/%d): %s", retry_count, MAX_RETRIES, exc
                    )
                    await asyncio.sleep(RETRY_BACKOFF_S * retry_count)

            if not success:
                try:
                    await send_to_dlq(
                        original_topic=msg.topic,
                        event=event,
                        retry_count=retry_count,
                        failure_reason="max retries exceeded",
                    )
                except DLQSendError:
                    logger.error(
                        "DLQ send failed for topic=%s event=%s retries=%d – committing anyway",
                        msg.topic, event.get("event_type"), retry_count,
                    )
                # Always commit to avoid infinite reprocessing
                await consumer.commit()
    except asyncio.CancelledError:
        logger.info("Kafka consumer cancelled, shutting down")
    except KafkaError as exc:
        logger.exception("Kafka consumer fatal error: %s", exc)
    except Exception as exc:
        logger.exception("Kafka consumer unexpected error: %s", exc)
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped")
