from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CarFindingPose(BaseModel):
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    frame_id: str = "map"


class ParkingSpot(BaseModel):
    spot_id: str
    name: str
    pose: CarFindingPose


class ParkingSpotListResponse(BaseModel):
    spots: List[ParkingSpot]


class BindPlateRequest(BaseModel):
    user_id: str = Field("demo_user", min_length=1, max_length=64)
    plate_number: str = Field(..., min_length=1, max_length=32)


class PlateBindingResponse(BaseModel):
    user_id: str
    plate_number: str
    normalized_plate_number: str
    updated_at: datetime


class ParkAtSpotOneRequest(BaseModel):
    user_id: str = Field("demo_user", min_length=1, max_length=64)
    plate_number: Optional[str] = Field(default=None, min_length=1, max_length=32)


class ParkingRecordResponse(BaseModel):
    user_id: str
    spot_id: str
    spot_name: str
    plate_number: str
    normalized_plate_number: str
    pose: CarFindingPose
    recorded_at: datetime


class GuideToSpotOneRequest(BaseModel):
    user_id: str = Field("demo_user", min_length=1, max_length=64)


class GuideToSpotOneResponse(BaseModel):
    user_id: str
    spot: ParkingSpot
    parking_record: ParkingRecordResponse
    nav_goal: Dict[str, Any]


class VerifyAtSpotOneRequest(BaseModel):
    user_id: str = Field("demo_user", min_length=1, max_length=64)
    topic_name: str = Field("/image_raw", description="ROS image topic used for plate detection")
    timeout_sec: float = Field(8.0, ge=0.5, le=30.0)
    robot_code: str = Field("robot_001", min_length=1, max_length=64)
    camera_code: Optional[str] = Field("usb_cam", max_length=64)


class VerifyPlateRequest(BaseModel):
    plate_number: str = Field(..., min_length=1, max_length=32)
    topic_name: str = Field("/image_raw", description="ROS image topic used for plate detection")
    timeout_sec: float = Field(8.0, ge=0.5, le=30.0)
    robot_code: str = Field("robot_001", min_length=1, max_length=64)
    camera_code: Optional[str] = Field("usb_cam", max_length=64)


class VerifyAtSpotOneResponse(BaseModel):
    user_id: str
    matched: bool
    expected_plate: str
    expected_normalized_plate: str
    detected_plates: List[str] = Field(default_factory=list)
    detected_normalized_plates: List[str] = Field(default_factory=list)
    parking_record: ParkingRecordResponse
    detection: Dict[str, Any]


class VerifyPlateResponse(BaseModel):
    matched: bool
    expected_plate: str
    expected_normalized_plate: str
    detected_plates: List[str] = Field(default_factory=list)
    detected_normalized_plates: List[str] = Field(default_factory=list)
    detection: Dict[str, Any]
