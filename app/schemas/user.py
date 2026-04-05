from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole, UserStatus


# ── Request schemas ──

class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    role: UserRole = UserRole.viewer


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    email: EmailStr | None = None
    role: UserRole | None = None
    status: UserStatus | None = None


# ── Response schemas ──

class UserOut(BaseModel):
    """Full user response – returned only to admin callers."""
    id: int
    name: str
    email: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserPublicOut(BaseModel):
    """Public user response – email is omitted."""
    id: int
    name: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
