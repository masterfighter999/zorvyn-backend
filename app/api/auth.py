"""Auth router – handle simple Mock authentication and JWT issuance."""

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User, UserRole, UserStatus
from app.repositories.user_repo import UserRepository

router = APIRouter(prefix="/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    email: EmailStr
    name: str = "New User"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Mock login: Find or create a user by email and issue a JWT."""
    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)

    if not user:
        # Create new user as a 'viewer' by default, or 'admin' if it's the default admin email
        assigned_role = UserRole.admin if body.email == "admin@zorvyn.com" else UserRole.viewer
        user = User(
            name=body.name,
            email=body.email,
            role=assigned_role,
            status=UserStatus.active
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Failsafe: if admin@zorvyn.com was somehow demoted in the database, promote them back
        if user.email == "admin@zorvyn.com" and user.role != UserRole.admin:
            user.role = UserRole.admin
            await db.commit()
            await db.refresh(user)
    
    # Issue JWT token
    role_value = user.role.value if hasattr(user.role, 'value') else user.role
    access_token = create_access_token({"sub": str(user.id), "role": role_value, "name": user.name})
    
    return TokenResponse(access_token=access_token)

