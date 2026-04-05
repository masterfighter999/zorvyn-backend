"""
Transactional Outbox Worker.

Polls the outbox_events table for pending and failed events and publishes them to Kafka.
Uses optimistic locking (SELECT FOR UPDATE SKIP LOCKED) to handle concurrent workers.

Flow:
  1. SELECT pending/failed outbox events (FOR UPDATE SKIP LOCKED)
  2. Publish each event to the appropriate Kafka topic
  3. Mark event as 'delivered' and set processed_at
  4. On Kafka failure → mark as 'failed' (retried on next poll)

The worker runs as a background asyncio task started on app lifespan.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, or_

from app.core.database import async_session
from app.kafka.producer import send_event, TOPIC_RECORDS, TOPIC_AUDIT, close_producer
from app.models.outbox import OutboxEvent

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 5        # seconds between polls
BATCH_SIZE = 50            # max events per poll cycle

# Map aggregate_type → Kafka topic
_TOPIC_MAP: dict[str, str] = {
    "record": TOPIC_RECORDS,
    "audit": TOPIC_AUDIT,
}


async def _publish_batch(events: list[OutboxEvent]) -> dict[int, bool]:
    """Publish a batch of outbox events. Returns {id: success}."""
    results: dict[int, bool] = {}
    for event in events:
        try:
            payload = json.loads(event.payload)
            topic = _TOPIC_MAP.get(event.aggregate_type, TOPIC_RECORDS)
            await send_event(
                topic=topic,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                payload=payload,
                key=str(event.aggregate_id),
            )
            results[event.id] = True
        except json.JSONDecodeError as exc:
            logger.error(
                "Outbox: malformed JSON in event id=%d error=%s", event.id, exc,
            )
            results[event.id] = False
        except Exception as exc:
            logger.error(
                "Outbox: failed to publish event id=%d type=%s error=%s",
                event.id, event.event_type, exc,
            )
            results[event.id] = False
    return results


async def _poll_and_publish() -> None:
    """Single poll cycle: fetch → publish → mark status."""
    async with async_session() as session:
        # SELECT … FOR UPDATE SKIP LOCKED – avoids concurrent worker collisions
        # Fetches both 'pending' and 'failed' events for retry
        stmt = (
            select(OutboxEvent)
            .where(or_(OutboxEvent.status == "pending", OutboxEvent.status == "failed"))
            .order_by(OutboxEvent.created_at)
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        events = list(result.scalars().all())

        if not events:
            return

        logger.debug("Outbox: processing %d event(s)", len(events))
        results = await _publish_batch(events)

        now = datetime.now(timezone.utc)
        for event in events:
            success = results.get(event.id, False)
            event.status = "delivered" if success else "failed"
            event.processed_at = now if success else None

        await session.commit()


async def run_outbox_worker(stop_event: asyncio.Event | None = None) -> None:
    """Main loop: poll on interval until stop_event is set."""
    logger.info("Outbox worker started (interval=%ds, batch=%d)", POLL_INTERVAL_S, BATCH_SIZE)
    while True:
        try:
            await _poll_and_publish()
        except Exception:
            logger.exception("Outbox worker: unexpected error in poll cycle")

        if stop_event:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL_S)
                break
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(POLL_INTERVAL_S)

    await close_producer()
    logger.info("Outbox worker stopped")
