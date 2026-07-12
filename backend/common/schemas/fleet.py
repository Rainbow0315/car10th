from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


FleetRobotStatus = Literal["online", "offline", "error"]
FleetRobotMode = Literal["idle", "teleop", "patrol", "follow", "busy"]


class FleetRobotSnapshot(BaseModel):
    robot_code: str
    status: FleetRobotStatus = "offline"
    mode: FleetRobotMode = "idle"
    battery: int = Field(0, ge=0, le=100)
    network_latency: int = Field(0, ge=0)
    pose_x: Optional[float] = None
    pose_y: Optional[float] = None
    pose_yaw: Optional[float] = None
    map_name: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    updated_at: datetime
    last_message_type: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class FleetRobotListResponse(BaseModel):
    robots: list[FleetRobotSnapshot]
    offline_after_sec: int
