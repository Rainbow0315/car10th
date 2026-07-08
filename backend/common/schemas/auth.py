from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, examples=["admin"])
    password: str = Field(..., min_length=1, max_length=128, examples=["admin123"])


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class RoleInfo(BaseModel):
    id: int
    role_code: str
    role_name: str
    permissions: Optional[list] = None

    model_config = {"from_attributes": True}


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    status: int
    last_login_at: Optional[datetime] = None
    role: RoleInfo

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo
