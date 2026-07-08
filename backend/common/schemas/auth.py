from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, examples=["admin"])
    password: str = Field(..., min_length=1, max_length=128, examples=["admin123"])


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, examples=["zhangsan"])
    password: str = Field(..., min_length=6, max_length=128, examples=["123456"])
    display_name: Optional[str] = Field(None, max_length=64, examples=["张三"])
    phone: Optional[str] = Field(None, max_length=20, examples=["13800138000"])
    email: Optional[str] = Field(None, max_length=128, examples=["user@example.com"])

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, value: str) -> str:
        if not value.replace("_", "").isalnum():
            raise ValueError("用户名只能包含字母、数字和下划线")
        return value


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
