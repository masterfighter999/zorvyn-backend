"""
Dead Letter Queue handler for Aiven Kafka.

When a consumer fails to process a message after max retries,
it calls send_to_dlq() which publishes a structured failure record
to the finance.dlq topic.
"""

import logging
from typing import Any

from app.kafka.producer import send_event, TOPIC_DLQ

logger = logging.getLogger(__name__)


class DLQSendError(RuntimeError):
    """Raised when an event cannot be sent to the Dead Letter Queue."""
    pass


async def send_to_dlq(
    original_topic: str,
    event: dict[str, Any],
    retry_count: int,
    failure_reason: str,
) -> None:
    """Publish a failed event to the dead letter queue.

    Raises DLQSendError if the DLQ publish itself fails.
    """
    dlq_payload = {
        "original_topic": original_topic,
        "event": event,
        "retry_count": retry_count,
        "failure_reason": failure_reason,
    }
    try:
        await send_event(
            topic=TOPIC_DLQ,
            event_type="DLQ_EVENT",
            aggregate_type=event.get("aggregate_type", "unknown"),
            aggregate_id=event.get("aggregate_id", 0),
            payload=dlq_payload,
        )
        logger.warning(
            "Event sent to DLQ: topic=%s event_type=%s retries=%d reason=%s",
            original_topic, event.get("event_type"), retry_count, failure_reason,
        )
    except Exception as exc:
        logger.error("Failed to send to DLQ — event lost!", exc_info=True)
        raise DLQSendError(f"DLQ send failed: {exc}") from exc
