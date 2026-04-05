from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date

from app.core.database import get_db
from app.core.security import require_role
from app.models.record import RecordType
from app.redis.client import get_redis
from app.schemas.record import DashboardSummary, CategoryBreakdown, TrendPoint, RecordOut, AggregationPeriod
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _svc(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> DashboardService:
    return DashboardService(db, redis)


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    current_user: dict = Depends(require_role("admin", "analyst", "viewer")),
    svc: DashboardService = Depends(_svc),
):
    return await svc.summary(current_user)


@router.get("/trends", response_model=list[TrendPoint])
async def dashboard_trends(
    period: AggregationPeriod = Query(default=AggregationPeriod.month),
    count: int = Query(default=6, ge=1, le=24),
    end_date: date | None = Query(default=None),
    current_user: dict = Depends(require_role("admin", "analyst")),
    svc: DashboardService = Depends(_svc),
):
    return await svc.trends(period, count, end_date, current_user)


@router.get("/categories", response_model=list[CategoryBreakdown])
async def dashboard_categories(
    type: RecordType | None = None,
    current_user: dict = Depends(require_role("admin", "analyst")),
    svc: DashboardService = Depends(_svc),
):
    return await svc.categories(type)


@router.get("/recent", response_model=list[RecordOut])
async def dashboard_recent(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(require_role("admin", "analyst", "viewer")),
    svc: DashboardService = Depends(_svc),
):
    return await svc.recent(limit)
