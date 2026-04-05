from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate, UserUpdate
from app.models.user import User, UserRole
from app.models.activity_log import ActivityLog


class UserService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)
        self.db = db

    async def create_user(self, data: UserCreate, performed_by: int) -> User:
        existing = await self.repo.get_by_email(data.email)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        try:
            user = await self.repo.create(data)
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        self.db.add(ActivityLog(
            user_id=performed_by, action="CREATE_USER",
            resource_type="user", resource_id=user.id,
        ))
        return user

    async def get_user(self, user_id: int) -> User:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    async def list_users(self, skip: int = 0, limit: int = 50) -> list[User]:
        return await self.repo.list_all(skip, limit)

    async def update_user(self, user_id: int, data: UserUpdate, performed_by: int) -> User:
        user = await self.get_user(user_id)
        
        # Prevent demoting the default admin
        if user.email == "admin@zorvyn.com" and data.role and data.role != UserRole.admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the default system admin"
            )

        updated = await self.repo.update(user, data)
        self.db.add(ActivityLog(
            user_id=performed_by, action="UPDATE_USER",
            resource_type="user", resource_id=user.id,
        ))
        return updated


    async def delete_user(self, user_id: int, performed_by: int) -> None:
        if user_id == performed_by:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account",
            )
        user = await self.get_user(user_id)
        self.db.add(ActivityLog(
            user_id=performed_by, action="DELETE_USER",
            resource_type="user", resource_id=user.id,
        ))
        await self.db.flush()  # persist activity log before deletion
        await self.repo.delete(user)
