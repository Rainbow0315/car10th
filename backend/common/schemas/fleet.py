from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


FleetRobotStatus = Literal["online", "offline", "error"]
FleetRobotMode = Literal["idle", "teleop", "patrol", "follow", "busy"]
FleetCommandStatus = Literal["pending", "published", "acked", "failed", "timeout"]


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
    agent_hostname: Optional[str] = None
    agent_version: Optional[str] = None
    agent_ip: Optional[str] = None
    formation_id: Optional[str] = None
    formation_role: Optional[str] = None
    formation_slot: Optional[int] = None
    last_seen_at: Optional[datetime] = None
    updated_at: datetime
    last_message_type: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class FleetRobotListResponse(BaseModel):
    robots: list[FleetRobotSnapshot]
    offline_after_sec: int


class FleetCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=64)
    payload: Dict[str, Any] = Field(default_factory=dict)


class FleetBatchCommandRequest(FleetCommandRequest):
    robot_codes: list[str] = Field(..., min_length=1, max_length=50)


class FleetCommandSnapshot(BaseModel):
    command_id: str
    robot_code: str
    command: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    topic: str
    status: FleetCommandStatus
    issued_at: datetime
    published_at: Optional[datetime] = None
    acked_at: Optional[datetime] = None
    ack: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class FleetBatchCommandResponse(BaseModel):
    commands: list[FleetCommandSnapshot]


class FleetFormationRequest(BaseModel):
    robot_codes: list[str] = Field(..., min_length=1, max_length=50)
    formation_type: str = Field("line", min_length=1, max_length=32)
    mode: str = Field("patrol", min_length=1, max_length=32)
    spacing_m: float = Field(1.0, ge=0.0, le=20.0)


class FleetFormationResponse(BaseModel):
    formation_id: str
    formation_type: str
    commands: list[FleetCommandSnapshot]


class FleetFormationMemberSnapshot(BaseModel):
    robot_code: str
    role: str
    slot_index: int
    offset_x: float
    offset_y: float
    command: FleetCommandSnapshot
    robot: FleetRobotSnapshot
    ready: bool


class FleetFormationSnapshot(BaseModel):
    formation_id: str
    formation_type: str
    mode: str
    created_at: datetime
    total_robots: int
    online_robots: int
    acked_commands: int
    ready: bool
    members: list[FleetFormationMemberSnapshot]


class FleetFormationListResponse(BaseModel):
    formations: list[FleetFormationSnapshot]
