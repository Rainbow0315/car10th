from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload

from apps.web_api.dependencies import get_client_ip, utcnow_naive
from common.config.settings import settings
from common.models import Role, User
from common.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserInfo,
)
from common.utils.security import create_access_token, hash_password, verify_password


class AuthService:
    DEFAULT_REGISTER_ROLE = "operator"

    def register(self, db: Session, payload: RegisterRequest, request: Request) -> TokenResponse:
        if db.query(User).filter(User.username == payload.username).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

        role = (
            db.query(Role)
            .filter(Role.role_code == self.DEFAULT_REGISTER_ROLE, Role.status == 1)
            .first()
        )
        if not role:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="默认角色未配置")

        user = User(
            username=payload.username,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name or payload.username,
            role_id=role.id,
            phone=payload.phone,
            email=payload.email,
            status=1,
            last_login_at=utcnow_naive(),
            last_login_ip=get_client_ip(request),
        )
        db.add(user)
        db.commit()

        user = (
            db.query(User)
            .options(joinedload(User.role))
            .filter(User.id == user.id)
            .first()
        )

        token = create_access_token(
            subject=user.username,
            extra={"uid": user.id, "role": role.role_code},
        )
        return TokenResponse(
            access_token=token,
            expires_in=settings.jwt_expire_minutes * 60,
            user=UserInfo.model_validate(user),
        )

    def login(self, db: Session, payload: LoginRequest, request: Request) -> TokenResponse:
        user = (
            db.query(User)
            .options(joinedload(User.role))
            .filter(User.username == payload.username)
            .first()
        )

        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        if user.status != 1:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")

        user.last_login_at = utcnow_naive()
        user.last_login_ip = get_client_ip(request)

        token = create_access_token(
            subject=user.username,
            extra={"uid": user.id, "role": user.role.role_code},
        )

        db.commit()
        db.refresh(user)

        return TokenResponse(
            access_token=token,
            expires_in=settings.jwt_expire_minutes * 60,
            user=UserInfo.model_validate(user),
        )

    def change_password(
        self,
        db: Session,
        user: User,
        payload: ChangePasswordRequest,
    ) -> dict:
        if not verify_password(payload.old_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")

        user.password_hash = hash_password(payload.new_password)
        db.commit()
        return {"message": "密码修改成功"}

    def get_me(self, user: User) -> UserInfo:
        return UserInfo.model_validate(user)


auth_service = AuthService()
