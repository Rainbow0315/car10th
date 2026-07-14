from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CmdVelRequest(BaseModel):
    linear_x: float = Field(..., description="Forward/backward velocity in m/s")
    linear_y: float = Field(0.0, description="Lateral velocity in m/s")
    angular_z: float = Field(0.0, description="Angular velocity in rad/s")
    duration: float = Field(0.3, ge=0.0, le=30.0, description="Publish duration in seconds")
    rate_hz: float = Field(10.0, ge=1.0, le=30.0, description="Publish rate while duration is active")
    wait_for_subscriber_timeout: float = Field(
        2.0,
        ge=0.0,
        le=10.0,
        description="How long to wait for at least one /cmd_vel subscriber before sending the command",
    )


class CmdVelAcceptedResponse(BaseModel):
    status: str
    mode: str
    topic_name: str
    subscriber_count: int
    waited_for_subscriber_timeout: float
    command: Dict[str, Any]


class RotateAngleRequest(BaseModel):
    angle_rad: float = Field(..., ge=-12.5664, le=12.5664, description="Target signed rotation angle in radians")
    angular_z: float = Field(0.6, ge=0.05, le=1.5, description="Maximum absolute angular velocity in rad/s")
    tolerance_rad: float = Field(0.08, ge=0.01, le=0.3, description="Acceptable angular error in radians")
    rate_hz: float = Field(20.0, ge=5.0, le=50.0, description="Closed-loop control publish rate")
    timeout_sec: float = Field(20.0, ge=1.0, le=60.0, description="Maximum time allowed for the rotation")
    wait_for_subscriber_timeout: float = Field(
        2.0,
        ge=0.0,
        le=10.0,
        description="How long to wait for at least one /cmd_vel subscriber before sending the command",
    )
    wait_for_odom_timeout: float = Field(
        2.0,
        ge=0.0,
        le=10.0,
        description="How long to wait for a fresh /odom yaw before starting closed-loop rotation",
    )


class RotateAngleResponse(BaseModel):
    status: str
    mode: str
    topic_name: str
    odom_topic: str
    subscriber_count: int
    command: Dict[str, Any]
    result: Dict[str, Any]


class StopResponse(BaseModel):
    status: str
    command: str
    topic_name: str
    subscriber_count: int


class RosBridgeHealthResponse(BaseModel):
    status: str
    service: str
    cmd_vel_topic: Optional[str] = None
    odom_topic: Optional[str] = None
    imu_topic: Optional[str] = None
    subscriber_count: int = 0
    odom_ready: bool = False
    yaw_source: Optional[str] = None
    node_name: Optional[str] = None
    startup_error: Optional[str] = None
