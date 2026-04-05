from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.record_repo import RecordRepository
from app.models.record import RecordType
from app.redis.cache import (
    get_cached, set_cached,
    summary_key, trends_key, categories_key, recent_key,
    SUMMARY_TTL, TRENDS_TTL, CATEGORIES_TTL, RECENT_TTL,
)
from app.schemas.record import RecordOut, AggregationPeriod


from datetime import date

class DashboardService:
    def __init__(self, db: AsyncSession, redis: Redis | None = None):
        self.repo = RecordRepository(db)
        self.redis = redis

    async def summary(self, current_user: dict) -> dict:
        if self.redis:
            key = summary_key(current_user["user_id"])
            cached = await get_cached(self.redis, key)
            if cached:
                return cached
        result = await self.repo.get_summary()
        if self.redis:
            await set_cached(self.redis, key, result, SUMMARY_TTL)
        return result

    async def trends(self, period: AggregationPeriod, count: int, end_date: date | None = None, current_user: dict | None = None) -> list[dict]:
        if self.redis and current_user:
            end_date_str = str(end_date) if end_date else "none"
            key = trends_key(current_user["user_id"], f"{period.value}_{count}_{end_date_str}")
            cached = await get_cached(self.redis, key)
            if cached:
                return cached
        result = await self.repo.get_trends(period, count, end_date)
        if self.redis and current_user:
            await set_cached(self.redis, key, result, TRENDS_TTL)
        return result

    async def categories(self, record_type: RecordType | None = None) -> list[dict]:
        if self.redis:
            key = categories_key(record_type.value if record_type else None)
            cached = await get_cached(self.redis, key)
            if cached:
                return cached
        result = await self.repo.get_category_breakdown(record_type)
        if self.redis:
            await set_cached(self.redis, key, result, CATEGORIES_TTL)
        return result

    async def recent(self, limit: int = 10) -> list[dict]:
        """Return recent records as serialised dicts (consistent type on hit or miss)."""
        if self.redis:
            key = recent_key(limit)
            cached = await get_cached(self.redis, key)
            if cached:
                return cached
        result = await self.repo.get_recent(limit)
        serialised = [RecordOut.model_validate(r).model_dump(mode="json") for r in result]
        if self.redis:
            await set_cached(self.redis, key, serialised, RECENT_TTL)
        return serialised
