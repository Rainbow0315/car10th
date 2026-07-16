from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.web_api.dependencies import require_permission
from apps.web_api.services.teleop_service import teleop_service
from common.models import User
from common.schemas.teleop import CmdVelAcceptedResponse, CmdVelRequest, RosBridgeHealthResponse, StopResponse

router = APIRouter()


@router.get("/health", response_model=RosBridgeHealthResponse, summary="ROS bridge health")
def teleop_health():
    return teleop_service.health()


@router.post("/cmd-vel", response_model=CmdVelAcceptedResponse, summary="Send /cmd_vel command")
def publish_cmd_vel(
    payload: CmdVelRequest,
    _: User = Depends(require_permission("robot:control")),
):
    return teleop_service.publish_cmd_vel(payload.model_dump())


@router.post("/stop", response_model=StopResponse, summary="Stop robot")
def stop_robot():
    return teleop_service.stop()
