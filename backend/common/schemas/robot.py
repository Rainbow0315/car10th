from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


RobotWorkMode = Literal["idle", "patrol", "follow", "teleop"]
RobotOnlineStatus = Literal["online", "offline", "error"]


class RobotStatusPayload(BaseModel):
    robot_code: str
    status: RobotOnlineStatus = "offline"
    mode: RobotWorkMode = "idle"
    battery: int = Field(0, ge=0, le=100)
    network_latency: int = Field(0, ge=0)
    pose_x: Optional[float] = None
    pose_y: Optional[float] = None
    pose_yaw: Optional[float] = None
    map_name: Optional[str] = None
    updated_at: datetime


class RobotControlRequest(BaseModel):
    robot_code: str = Field(..., examples=["robot_001"])
    command: str = Field(
        ...,
        description="cmd_vel | stop | patrol_start | patrol_stop | mode_follow",
        examples=["cmd_vel"],
    )
    payload: Dict[str, Any] = Field(default_factory=dict)


class RobotControlResponse(BaseModel):
    robot_code: str
    command: str
    status: str
    detail: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class AlarmNotifyPayload(BaseModel):
    alarm_no: str
    robot_code: str
    alarm_type: str
    risk_level: str
    confidence: float
    image_url: Optional[str] = None
    pos_x: float
    pos_y: float
    detected_at: datetime
    description: Optional[str] = None


class MqttHealthResponse(BaseModel):
    connected: bool
    broker: str
    client_id: str
    last_error: Optional[str] = None
