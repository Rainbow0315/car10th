from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


FleetRobotStatus = Literal["online", "offline", "error"]
FleetRobotMode = Literal["idle", "teleop", "patrol", "follow", "busy", "rescue"]
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
    rescue_incident_id: Optional[str] = None
    rescue_target_robot_code: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    updated_at: datetime
    last_message_type: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class FleetRobotListResponse(BaseModel):
    robots: list[FleetRobotSnapshot]
    offline_after_sec: int


class FleetReadinessRequest(BaseModel):
    robot_codes: list[str] = Field(..., min_length=1, max_length=50)


class FleetReadinessMember(BaseModel):
    robot_code: str
    status: FleetRobotStatus
    online: bool
    ready_to_command: bool
    reason: Optional[str] = None
    robot: FleetRobotSnapshot


class FleetReadinessResponse(BaseModel):
    all_ready: bool
    total_robots: int
    ready_robots: int
    members: list[FleetReadinessMember]
    offline_after_sec: int


class FleetSummaryResponse(BaseModel):
    generated_at: datetime
    total_robots: int
    online_robots: int
    offline_robots: int
    error_robots: int
    total_commands: int
    pending_commands: int
    published_commands: int
    acked_commands: int
    failed_commands: int
    timeout_commands: int
    total_formations: int
    ready_formations: int


class FleetCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=64)
    payload: Dict[str, Any] = Field(default_factory=dict)


class FleetBatchCommandRequest(FleetCommandRequest):
    robot_codes: list[str] = Field(..., min_length=1, max_length=50)
    require_all_ready: bool = False


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


class FleetCommandListResponse(BaseModel):
    commands: list[FleetCommandSnapshot]
    total: int
    limit: int


class FleetBatchCommandResponse(BaseModel):
    commands: list[FleetCommandSnapshot]


class FleetRescueRequest(BaseModel):
    disabled_robot_code: str = Field(..., min_length=1, max_length=32)
    responder_robot_code: Optional[str] = Field(default=None, min_length=1, max_length=32)
    incident_type: str = Field("breakdown", min_length=1, max_length=32)
    note: Optional[str] = Field(default=None, max_length=256)
    require_responder_ready: bool = True


class FleetRescueResponse(BaseModel):
    incident_id: str
    disabled_robot_code: str
    responder_robot_code: str
    incident_type: str
    command: FleetCommandSnapshot
    disabled_robot: FleetRobotSnapshot
    responder_robot: FleetRobotSnapshot


class FleetRescueApproachRequest(BaseModel):
    responder_robot_code: str = Field(..., min_length=1, max_length=32)
    disabled_robot_code: Optional[str] = Field(default=None, min_length=1, max_length=32)
    incident_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    linear_x: float = Field(0.08, ge=0.0, le=0.12)
    angular_z: float = Field(0.0, ge=-0.4, le=0.4)
    duration: float = Field(0.8, ge=0.1, le=2.0)
    require_responder_ready: bool = True


class FleetRescueApproachResponse(BaseModel):
    responder_robot_code: str
    disabled_robot_code: Optional[str] = None
    incident_id: Optional[str] = None
    command: FleetCommandSnapshot


class FleetSafetyStopRequest(BaseModel):
    robot_codes: Optional[list[str]] = Field(default=None, max_length=50)
    incident_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    reason: str = Field("underground safety control", min_length=1, max_length=128)


class FleetSafetyStopResponse(BaseModel):
    target_robots: list[str]
    commands: list[FleetCommandSnapshot]


class FleetFormationRequest(BaseModel):
    robot_codes: list[str] = Field(..., min_length=1, max_length=50)
    formation_type: str = Field("line", min_length=1, max_length=32)
    mode: str = Field("patrol", min_length=1, max_length=32)
    spacing_m: float = Field(1.0, ge=0.0, le=20.0)
    require_all_ready: bool = False


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
