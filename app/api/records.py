from datetime import date

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.record import RecordType
from app.redis.client import get_redis
from app.schemas.record import RecordCreate, RecordUpdate, RecordOut
from app.services.record_service import RecordService

router = APIRouter(prefix="/records", tags=["Records"])


def _svc(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> RecordService:
    return RecordService(db, redis)


@router.post("", response_model=RecordOut, status_code=status.HTTP_201_CREATED)
async def create_record(
    body: RecordCreate,
    current_user: dict = Depends(require_role("admin")),
    svc: RecordService = Depends(_svc),
):
    return await svc.create_record(body, created_by=current_user["user_id"])


@router.get("", response_model=list[RecordOut])
async def list_records(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    type: RecordType | None = None,
    category: str | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    current_user: dict = Depends(require_role("admin", "analyst")),
    svc: RecordService = Depends(_svc),
):
    return await svc.list_records(skip, limit, type, category, date_from, date_to)


@router.get("/{record_id}", response_model=RecordOut)
async def get_record(
    record_id: int,
    current_user: dict = Depends(require_role("admin", "analyst")),
    svc: RecordService = Depends(_svc),
):
    return await svc.get_record(record_id)


@router.patch("/{record_id}", response_model=RecordOut)
async def update_record(
    record_id: int,
    body: RecordUpdate,
    current_user: dict = Depends(require_role("admin")),
    svc: RecordService = Depends(_svc),
):
    return await svc.update_record(record_id, body, updated_by=current_user["user_id"])


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
    record_id: int,
    current_user: dict = Depends(require_role("admin")),
    svc: RecordService = Depends(_svc),
):
    await svc.delete_record(record_id, deleted_by=current_user["user_id"])
