from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


PatrolTaskStatus = Literal["draft", "pending", "running", "completed", "failed", "cancelled"]


class PatrolWaypoint(BaseModel):
    seq: int = Field(..., ge=1)
    x: float
    y: float
    yaw: float = 0.0
    name: str = Field("", max_length=128)


class PatrolTaskCreateRequest(BaseModel):
    task_name: str = Field(..., min_length=1, max_length=128)
    robot_code: str = Field("robot_001", min_length=1, max_length=32)
    waypoints: List[PatrolWaypoint] = Field(..., min_length=2)
    loop_count: int = Field(1, ge=1, le=999)
    schedule_cron: Optional[str] = Field(None, max_length=64)
    return_to_start: bool = True
    detection_config: Optional[Dict[str, Any]] = None


class PatrolTaskUpdateRequest(BaseModel):
    task_name: Optional[str] = Field(None, min_length=1, max_length=128)
    robot_code: Optional[str] = Field(None, min_length=1, max_length=32)
    waypoints: Optional[List[PatrolWaypoint]] = Field(None, min_length=2)
    loop_count: Optional[int] = Field(None, ge=1, le=999)
    schedule_cron: Optional[str] = Field(None, max_length=64)
    return_to_start: Optional[bool] = None
    detection_config: Optional[Dict[str, Any]] = None


class PatrolTaskPayload(BaseModel):
    task_code: str
    task_name: str
    robot_code: str
    waypoints: List[PatrolWaypoint] = Field(default_factory=list)
    schedule_cron: Optional[str] = None
    loop_count: int = 1
    return_to_start: bool = True
    status: PatrolTaskStatus = "draft"
    trigger_type: str = "manual"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PatrolTaskListResponse(BaseModel):
    items: List[PatrolTaskPayload] = Field(default_factory=list)


class PatrolTaskStartResponse(BaseModel):
    task_code: str
    status: str
    detail: str


class PatrolTaskStopResponse(BaseModel):
    task_code: str
    status: str
    detail: str


class PatrolRuntimePayload(BaseModel):
    task_code: str
    running: bool
    state: str
    robot_code: str
    current_seq: Optional[int] = None
    current_goal: Optional[PatrolWaypoint] = None
    last_pose: Optional[Dict[str, float]] = None
    message: Optional[str] = None
    updated_at: datetime

