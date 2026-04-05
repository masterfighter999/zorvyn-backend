from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


def _svc(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    current_user: dict = Depends(require_role("admin")),
    svc: UserService = Depends(_svc),
):
    return await svc.create_user(body, performed_by=current_user["user_id"])


@router.get("", response_model=list[UserOut])
async def list_users(
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(require_role("admin")),
    svc: UserService = Depends(_svc),
):
    return await svc.list_users(skip, limit)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
    svc: UserService = Depends(_svc),
):
    return await svc.get_user(user_id)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    current_user: dict = Depends(require_role("admin")),
    svc: UserService = Depends(_svc),
):
    return await svc.update_user(user_id, body, performed_by=current_user["user_id"])


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
    svc: UserService = Depends(_svc),
):
    await svc.delete_user(user_id, performed_by=current_user["user_id"])
