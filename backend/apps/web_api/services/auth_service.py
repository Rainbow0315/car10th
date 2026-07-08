from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload

from apps.web_api.dependencies import get_client_ip, utcnow_naive
from common.config.settings import settings
from common.models import OperationLog, User
from common.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse, UserInfo
from common.utils.security import create_access_token, hash_password, verify_password


class AuthService:
    def login(self, db: Session, payload: LoginRequest, request: Request) -> TokenResponse:
        user = (
            db.query(User)
            .options(joinedload(User.role))
            .filter(User.username == payload.username)
            .first()
        )

        if not user or not verify_password(payload.password, user.password_hash):
            self._write_log(
                db,
                user=None,
                username=payload.username,
                action_type="login_failed",
                action_desc="登录失败：用户名或密码错误",
                request=request,
                response_code=401,
            )
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        if user.status != 1:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")

        ip = get_client_ip(request)
        user.last_login_at = utcnow_naive()
        user.last_login_ip = ip

        token = create_access_token(
            subject=user.username,
            extra={"uid": user.id, "role": user.role.role_code},
        )

        self._write_log(
            db,
            user=user,
            username=user.username,
            action_type="login",
            action_desc="用户登录成功",
            request=request,
            response_code=200,
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
        request: Request,
    ) -> dict:
        if not verify_password(payload.old_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")

        user.password_hash = hash_password(payload.new_password)
        self._write_log(
            db,
            user=user,
            username=user.username,
            action_type="change_password",
            action_desc="用户修改密码",
            request=request,
            response_code=200,
        )
        db.commit()
        return {"message": "密码修改成功"}

    def get_me(self, user: User) -> UserInfo:
        return UserInfo.model_validate(user)

    def _write_log(
        self,
        db: Session,
        user: Optional[User],
        username: Optional[str],
        action_type: str,
        action_desc: str,
        request: Request,
        response_code: int,
    ) -> None:
        log = OperationLog(
            user_id=user.id if user else None,
            username=username,
            module="auth",
            action_type=action_type,
            action_desc=action_desc,
            request_method=request.method,
            request_url=str(request.url.path),
            response_code=response_code,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
        db.add(log)


auth_service = AuthService()
