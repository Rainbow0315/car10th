from __future__ import annotations

from typing import Any

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
    command: dict[str, Any]


class StopResponse(BaseModel):
    status: str
    command: str
    topic_name: str
    subscriber_count: int


class RosBridgeHealthResponse(BaseModel):
    status: str
    service: str
    cmd_vel_topic: str | None = None
    subscriber_count: int = 0
    node_name: str | None = None
    startup_error: str | None = None
