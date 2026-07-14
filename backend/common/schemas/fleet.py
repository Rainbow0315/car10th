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
    escort_mission_id: Optional[str] = None
    escort_target_robot_code: Optional[str] = None
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


class FleetTeleopCommandRequest(BaseModel):
    robot_codes: list[str] = Field(..., min_length=1, max_length=20)
    linear_x: float = Field(0.12, ge=-0.3, le=0.3)
    linear_y: float = Field(0.0, ge=-0.3, le=0.3)
    angular_z: float = Field(0.0, ge=-1.0, le=1.0)
    duration: float = Field(5.0, ge=0.0, le=10.0)
    rate_hz: float = Field(10.0, ge=1.0, le=30.0)
    wait_for_subscriber_timeout: float = Field(1.0, ge=0.0, le=5.0)
    require_all_ready: bool = False


class FleetTeleopStopRequest(BaseModel):
    robot_codes: list[str] = Field(..., min_length=1, max_length=20)
    require_all_ready: bool = False


class FleetTeleopMemberResponse(BaseModel):
    robot_code: str
    ros_bridge_url: str
    ok: bool
    status_code: Optional[int] = None
    elapsed_ms: float
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class FleetTeleopResponse(BaseModel):
    target_robots: list[str]
    all_ok: bool
    command: str
    requested_duration: Optional[float] = None
    effective_duration: Optional[float] = None
    duration_compensation: Optional[float] = None
    requested_rate_hz: Optional[float] = None
    effective_rate_hz: Optional[float] = None
    members: list[FleetTeleopMemberResponse]


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


class FleetRescueSearchRequest(BaseModel):
    responder_robot_code: str = Field(..., min_length=1, max_length=32)
    disabled_robot_code: Optional[str] = Field(default=None, min_length=1, max_length=32)
    incident_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    angular_z: float = Field(0.25, ge=0.1, le=0.4)
    duration: float = Field(1.5, ge=0.5, le=3.0)
    require_responder_ready: bool = True


class FleetRescueSearchResponse(BaseModel):
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


class FleetCorridorCrawlRequest(BaseModel):
    robot_codes: list[str] = Field(..., min_length=1, max_length=50)
    corridor_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    linear_x: float = Field(0.06, ge=0.0, le=0.12)
    duration: float = Field(1.0, ge=0.2, le=3.0)
    spacing_m: float = Field(1.0, ge=0.3, le=5.0)
    start_interval_sec: float = Field(0.0, ge=0.0, le=5.0)
    require_all_ready: bool = True


class FleetCorridorCrawlSlot(BaseModel):
    robot_code: str
    slot_index: int
    start_delay_sec: float


class FleetCorridorCrawlResponse(BaseModel):
    corridor_id: Optional[str] = None
    robot_codes: list[str]
    start_interval_sec: float
    schedule: list[FleetCorridorCrawlSlot]
    commands: list[FleetCommandSnapshot]


class FleetCorridorYieldRequest(BaseModel):
    yielding_robot_code: str = Field(..., min_length=1, max_length=32)
    priority_robot_code: Optional[str] = Field(default=None, min_length=1, max_length=32)
    corridor_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    linear_x: float = Field(-0.05, ge=-0.08, le=0.0)
    duration: float = Field(0.8, ge=0.2, le=2.0)
    reason: str = Field("yield for priority robot in underground corridor", min_length=1, max_length=128)
    require_yielding_ready: bool = True


class FleetCorridorYieldResponse(BaseModel):
    yielding_robot_code: str
    priority_robot_code: Optional[str] = None
    corridor_id: Optional[str] = None
    command: FleetCommandSnapshot


class FleetHazardAvoidanceRequest(BaseModel):
    robot_codes: Optional[list[str]] = Field(default=None, max_length=50)
    hazard_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    reported_by_robot_code: Optional[str] = Field(default=None, min_length=1, max_length=32)
    avoid_direction: Literal["left", "right"] = "left"
    linear_x: float = Field(0.04, ge=0.0, le=0.1)
    angular_z: float = Field(0.22, ge=0.1, le=0.4)
    duration: float = Field(1.0, ge=0.2, le=3.0)
    reason: str = Field("avoid underground hazard", min_length=1, max_length=128)
    require_all_ready: bool = True


class FleetHazardAvoidanceResponse(BaseModel):
    target_robots: list[str]
    hazard_id: Optional[str] = None
    reported_by_robot_code: Optional[str] = None
    avoid_direction: Literal["left", "right"]
    commands: list[FleetCommandSnapshot]


class FleetEscortReturnRequest(BaseModel):
    target_robot_code: str = Field(..., min_length=1, max_length=32)
    escort_robot_code: str = Field(..., min_length=1, max_length=32)
    maintenance_zone_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    target_plate_number: Optional[str] = Field(default=None, min_length=1, max_length=32)
    recognition_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reason: str = Field("low battery or fault escort return", min_length=1, max_length=128)
    escort_position: Literal["rear", "left", "right"] = "rear"
    linear_x: float = Field(0.05, ge=0.0, le=0.1)
    angular_z: float = Field(0.0, ge=-0.3, le=0.3)
    duration: float = Field(1.0, ge=0.2, le=3.0)
    require_escort_ready: bool = True


class FleetEscortReturnResponse(BaseModel):
    mission_id: str
    target_robot_code: str
    escort_robot_code: str
    maintenance_zone_id: Optional[str] = None
    target_plate_number: Optional[str] = None
    recognition_confidence: Optional[float] = None
    command: FleetCommandSnapshot


class FleetPlateVerifyRequest(BaseModel):
    verifier_robot_code: str = Field(..., min_length=1, max_length=32)
    plate_number: str = Field(..., min_length=1, max_length=32)
    recognition_confidence: float = Field(..., ge=0.0, le=1.0)
    zone_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    source_camera_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    bbox: Optional[list[int]] = Field(default=None, min_length=4, max_length=4)
    note: Optional[str] = Field(default=None, max_length=128)
    angular_z: float = Field(0.22, ge=0.1, le=0.4)
    duration: float = Field(1.5, ge=0.5, le=3.0)
    require_verifier_ready: bool = True


class FleetPlateVerifyResponse(BaseModel):
    verification_id: str
    verifier_robot_code: str
    plate_number: str
    recognition_confidence: float
    zone_id: Optional[str] = None
    source_camera_id: Optional[str] = None
    command: FleetCommandSnapshot


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
