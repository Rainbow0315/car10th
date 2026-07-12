from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class DetectionItem(BaseModel):
    label: str
    confidence: float
    bbox: List[float] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)


class DetectorResult(BaseModel):
    model: str
    count: int = 0
    detections: List[DetectionItem] = Field(default_factory=list)
    error: Optional[str] = None


class InspectionSummary(BaseModel):
    total_detections: int = 0
    has_risk: bool = False
    labels: Dict[str, int] = Field(default_factory=dict)
    completed_models: List[str] = Field(default_factory=list)
    failed_models: List[str] = Field(default_factory=list)


class ImageInspectionRequest(BaseModel):
    image_path: str = Field(..., description="本地图片绝对路径或相对 backend 工作目录的路径")
    robot_code: str = Field("robot_001", description="机器人编码")
    camera_code: Optional[str] = Field(None, description="摄像头编码")
    enabled_models: List[str] = Field(
        default_factory=lambda: ["crack", "puddle", "fod"],
        description="可选：crack / puddle / fod",
    )
    save_annotated: bool = Field(True, description="是否保存标注图")
    output_dir: Optional[str] = Field(None, description="可选：输出目录，未填时写入默认 runtime 目录")


class ImageInspectionResponse(BaseModel):
    image_path: str
    robot_code: str
    camera_code: Optional[str] = None
    device: str
    detected_at: datetime
    summary: InspectionSummary
    results: Dict[str, DetectorResult] = Field(default_factory=dict)
    annotated_image_path: Optional[str] = None


class SourceInspectionRequest(BaseModel):
    source: str = Field(
        ...,
        description="输入源：本地图片、本地视频、RTSP、MJPEG/HTTP 流，或摄像头索引字符串如 0",
    )
    robot_code: str = Field("robot_001", description="机器人编码")
    camera_code: Optional[str] = Field(None, description="摄像头编码")
    enabled_models: List[str] = Field(
        default_factory=lambda: ["crack", "puddle", "fod"],
        description="可选：crack / puddle / fod",
    )
    frame_index: int = Field(0, ge=0, description="视频文件抓帧索引，仅对本地视频生效")
    warmup_frames: int = Field(5, ge=0, le=60, description="流输入预热读取帧数")
    save_frame: bool = Field(True, description="是否保存抓取到的原始帧")
    save_annotated: bool = Field(True, description="是否保存标注图")
    output_dir: Optional[str] = Field(None, description="可选：输出目录，未填时写入默认 runtime 目录")


class SourceInspectionResponse(ImageInspectionResponse):
    source: str
    source_kind: Literal["image", "video", "stream", "camera_index"]
    frame_index: int = 0
