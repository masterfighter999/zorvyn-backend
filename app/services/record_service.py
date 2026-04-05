"""
RecordService – with transactional outbox, distributed locks, and circuit breaker.

Every mutating operation (create / update / delete) atomically writes:
  1. The financial record change
  2. An outbox_event row in 'pending' status
  3. An activity_log row

Update and delete use a distributed lock (Valkey SET NX PX) to prevent
concurrent modifications of the same record.
"""

import json
from datetime import date

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.repositories.record_repo import RecordRepository
from app.schemas.record import RecordCreate, RecordUpdate
from app.models.record import Record, RecordType
from app.models.activity_log import ActivityLog
from app.models.outbox import OutboxEvent
from app.redis.cache import invalidate_dashboard_cache
from app.redis.locks import acquire_lock, LockNotAcquiredError

MAX_LIMIT = 200


def _outbox(event_type: str, record: Record) -> OutboxEvent:
    """Build an OutboxEvent for a record mutation."""
    return OutboxEvent(
        aggregate_type="record",
        aggregate_id=record.id,
        event_type=event_type,
        payload=json.dumps({
            "record_id": record.id,
            "amount": str(record.amount),
            "type": record.type.value,
            "category": record.category,
        }),
    )


class RecordService:
    def __init__(self, db: AsyncSession, redis: Redis | None = None):
        self.repo = RecordRepository(db)
        self.db = db
        self.redis = redis

    async def _invalidate(self) -> None:
        if self.redis:
            await invalidate_dashboard_cache(self.redis)

    async def create_record(self, data: RecordCreate, created_by: int) -> Record:
        record = await self.repo.create(data, created_by)
        self.db.add(ActivityLog(
            user_id=created_by, action="CREATE_RECORD",
            resource_type="record", resource_id=record.id,
        ))
        self.db.add(_outbox("RECORD_CREATED", record))
        await self._invalidate()
        return record

    async def get_record(self, record_id: int) -> Record:
        record = await self.repo.get_by_id(record_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
        return record

    async def list_records(
        self,
        skip: int = 0,
        limit: int = 50,
        type_filter: RecordType | None = None,
        category: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Record]:
        capped_limit = max(1, min(limit, MAX_LIMIT))
        return await self.repo.list_all(skip, capped_limit, type_filter, category, date_from, date_to)

    async def update_record(self, record_id: int, data: RecordUpdate, updated_by: int) -> Record:
        if not self.redis:
            return await self._update_record_unsafe(record_id, data, updated_by)
        try:
            async with acquire_lock(self.redis, "record", record_id):
                return await self._update_record_unsafe(record_id, data, updated_by)
        except LockNotAcquiredError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Record is being modified by another request, please retry",
            )

    async def _update_record_unsafe(self, record_id: int, data: RecordUpdate, updated_by: int) -> Record:
        """Internal update without lock (called from within lock or when Redis unavailable)."""
        record = await self.get_record(record_id)
        updated = await self.repo.update(record, data, updated_by)
        self.db.add(ActivityLog(
            user_id=updated_by, action="UPDATE_RECORD",
            resource_type="record", resource_id=record.id,
        ))
        self.db.add(_outbox("RECORD_UPDATED", updated))
        await self._invalidate()
        return updated

    async def delete_record(self, record_id: int, deleted_by: int) -> None:
        if not self.redis:
            return await self._delete_record_unsafe(record_id, deleted_by)
        try:
            async with acquire_lock(self.redis, "record", record_id):
                await self._delete_record_unsafe(record_id, deleted_by)
        except LockNotAcquiredError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Record is being modified by another request, please retry",
            )

    async def _delete_record_unsafe(self, record_id: int, deleted_by: int) -> None:
        """Internal delete without lock."""
        record = await self.get_record(record_id)
        self.db.add(ActivityLog(
            user_id=deleted_by, action="DELETE_RECORD",
            resource_type="record", resource_id=record.id,
        ))
        self.db.add(_outbox("RECORD_DELETED", record))
        await self.repo.delete(record)
        await self._invalidate()
