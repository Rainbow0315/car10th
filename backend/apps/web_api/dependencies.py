from datetime import datetime, timezone
from typing import Iterable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload

from common.config.database import get_db
from common.config.settings import settings
from common.models import User
from common.utils.security import safe_decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = safe_decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.username == username)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.status != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    return user


def _permission_set(user: User) -> set[str]:
    permissions = []
    if user.role is not None and isinstance(user.role.permissions, list):
        permissions = user.role.permissions
    return {str(item) for item in permissions if item is not None}


def has_permission(user: User, required: str | Iterable[str]) -> bool:
    permissions = _permission_set(user)
    if "*" in permissions:
        return True
    if isinstance(required, str):
        required_permissions = {required}
    else:
        required_permissions = {str(item) for item in required}
    return bool(permissions.intersection(required_permissions))


def require_permission(required: str | Iterable[str]):
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user, required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前角色无权执行该操作",
            )
        return current_user

    return dependency


def get_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
