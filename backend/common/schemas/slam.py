from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SlamMapOrigin(BaseModel):
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0


class SlamPose(BaseModel):
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0


class SlamScanPoint(BaseModel):
    x: float = 0.0
    y: float = 0.0


class SlamMapResponse(BaseModel):
    available: bool
    frame_id: Optional[str] = None
    stamp_sec: Optional[int] = None
    stamp_nanosec: Optional[int] = None
    width: int = 0
    height: int = 0
    resolution: float = 0.0
    origin: SlamMapOrigin = Field(default_factory=SlamMapOrigin)
    robot_pose: Optional[SlamPose] = None
    laser_points: List[SlamScanPoint] = Field(default_factory=list)
    data: List[int] = Field(default_factory=list)


class SlamGoalRequest(BaseModel):
    x: float = Field(..., description="Goal x coordinate in map frame")
    y: float = Field(..., description="Goal y coordinate in map frame")
    yaw: float = Field(0.0, description="Goal heading in radians")
    frame_id: str = Field("map", description="Target coordinate frame")


class SlamGoalResponse(BaseModel):
    status: str
    topic_name: str
    frame_id: str
    goal: SlamPose


class SlamInitialPoseRequest(BaseModel):
    x: float = Field(..., description="Current robot x coordinate in map frame")
    y: float = Field(..., description="Current robot y coordinate in map frame")
    yaw: float = Field(0.0, description="Current robot heading in radians")
    frame_id: str = Field("map", description="Target coordinate frame")


class SlamInitialPoseResponse(BaseModel):
    status: str
    topic_name: str
    frame_id: str
    pose: SlamPose
