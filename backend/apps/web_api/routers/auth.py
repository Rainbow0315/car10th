from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload

from apps.web_api.dependencies import get_current_user
from apps.web_api.services.auth_service import auth_service
from common.config.database import get_db
from common.models import User
from common.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse, UserInfo

router = APIRouter()


@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return auth_service.login(db, payload, request)


@router.get("/me", response_model=UserInfo, summary="获取当前登录用户信息")
def get_me(current_user: User = Depends(get_current_user)):
    return auth_service.get_me(current_user)


@router.post("/change-password", summary="修改密码")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.id == current_user.id)
        .first()
    )
    return auth_service.change_password(db, user, payload, request)
