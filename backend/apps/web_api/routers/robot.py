from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.web_api.dependencies import get_current_user, require_permission
from apps.web_api.services.mqtt_service import mqtt_service
from apps.web_api.services.robot_service import robot_service
from common.config.database import get_db
from common.models import User
from common.schemas.robot import MqttHealthResponse, RobotControlRequest, RobotControlResponse, RobotStatusPayload

router = APIRouter()


@router.get("/mqtt/health", response_model=MqttHealthResponse, summary="MQTT 连接状态")
def mqtt_health():
    return mqtt_service.health()


@router.get("/robot/status", response_model=RobotStatusPayload, summary="获取单车状态")
def get_robot_status(
    robot_code: str = Query("robot_001", description="机器人编码"),
    _: User = Depends(get_current_user),
):
    return robot_service.get_status(robot_code)


@router.get("/robot/status/all", response_model=List[RobotStatusPayload], summary="获取全部小车状态")
def list_robot_status(_: User = Depends(get_current_user)):
    return robot_service.list_status()


@router.post("/robot/control", response_model=RobotControlResponse, summary="下发控制指令")
def control_robot(
    payload: RobotControlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("robot:control")),
):
    result = mqtt_service.control_via_rest(db, current_user.id, payload)
    return RobotControlResponse(**result)
