from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from apps.web_api.services.inspection_alarm_service import inspection_alarm_service
from apps.web_api.services.inspection_monitor_service import inspection_monitor_service
from apps.web_api.services.inspection_service import inspection_service
from common.config.database import get_db
from common.schemas.inspection import (
    AlarmHandleRequest,
    AlarmListResponse,
    AlarmLogResponse,
    ImageInspectionRequest,
    ImageInspectionResponse,
    InspectionMonitorStartRequest,
    InspectionMonitorStatusResponse,
    RosTopicInspectionRequest,
)

router = APIRouter()


@router.get("/health", summary="AI service health")
def inspection_health():
    return inspection_service.health()


@router.post("/detect-image", response_model=ImageInspectionResponse, summary="Run road inspection on one image")
def detect_image(payload: ImageInspectionRequest):
    return inspection_service.detect_image(payload.model_dump())


@router.post("/detect-ros-image", response_model=ImageInspectionResponse, summary="Capture one ROS image frame and inspect it")
def detect_ros_image(payload: RosTopicInspectionRequest):
    return inspection_service.detect_ros_image(payload.model_dump())


@router.get("/camera/snapshot", summary="Capture one ROS camera frame as JPEG")
def camera_snapshot(
    topic_name: str = Query("/image_raw", description="ROS image topic"),
    timeout_sec: float = Query(3.0, ge=0.5, le=10.0, description="Frame wait timeout in seconds"),
):
    content, media_type = inspection_service.camera_snapshot(topic_name, timeout_sec)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/camera/status", summary="Camera frame cache status")
def camera_status():
    return inspection_service.camera_status()


@router.get("/camera/mjpeg", summary="Stream ROS camera frames as MJPEG")
def camera_mjpeg(
    topic_name: str = Query("/image_raw", description="ROS image topic"),
    fps: float = Query(5.0, ge=0.5, le=10.0, description="MJPEG frame rate"),
    timeout_sec: float = Query(3.0, ge=0.5, le=10.0, description="Frame wait timeout in seconds"),
):
    return StreamingResponse(
        inspection_service.camera_mjpeg_stream(topic_name, fps, timeout_sec),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/monitor/start", response_model=InspectionMonitorStatusResponse, summary="Start continuous ROS image inspection")
async def start_monitor(payload: InspectionMonitorStartRequest):
    return await inspection_monitor_service.start(payload)


@router.post("/monitor/stop", response_model=InspectionMonitorStatusResponse, summary="Stop continuous ROS image inspection")
async def stop_monitor():
    return await inspection_monitor_service.stop()


@router.get("/monitor/status", response_model=InspectionMonitorStatusResponse, summary="Continuous inspection status")
def monitor_status():
    return inspection_monitor_service.status()


@router.post("/monitor/inspect-once", summary="Run one monitor iteration and persist risk alarms")
async def inspect_once(payload: InspectionMonitorStartRequest):
    return await inspection_monitor_service.inspect_once(payload)


@router.get("/alarms", response_model=AlarmListResponse, summary="List persisted inspection alarms")
def list_alarms(
    status: Optional[str] = Query(None, description="pending / processing / closed"),
    alarm_type: Optional[str] = Query(None, description="crack / water / foreign_object / other"),
    risk_level: Optional[str] = Query(None, description="low / medium / high"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        alarms = inspection_alarm_service.list_alarms(
            db,
            status=status,
            alarm_type=alarm_type,
            risk_level=risk_level,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AlarmListResponse(
        items=[inspection_alarm_service.to_response(alarm) for alarm in alarms],
        total=len(alarms),
    )


@router.get("/alarms/{alarm_id_or_no}", response_model=AlarmLogResponse, summary="Get persisted inspection alarm")
def get_alarm(alarm_id_or_no: str, db: Session = Depends(get_db)):
    alarm = inspection_alarm_service.get_alarm(db, alarm_id_or_no)
    if alarm is None:
        raise HTTPException(status_code=404, detail=f"alarm not found: {alarm_id_or_no}")
    return inspection_alarm_service.to_response(alarm)


@router.get("/alarms/{alarm_id_or_no}/image", summary="Get persisted inspection alarm image")
def get_alarm_image(alarm_id_or_no: str, db: Session = Depends(get_db)):
    alarm = inspection_alarm_service.get_alarm(db, alarm_id_or_no)
    if alarm is None:
        raise HTTPException(status_code=404, detail=f"alarm not found: {alarm_id_or_no}")
    image_path = Path(alarm.image_path)
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail=f"alarm image not found: {alarm.image_path}")
    return FileResponse(image_path)


@router.post("/alarms/{alarm_id_or_no}/handle", response_model=AlarmLogResponse, summary="Mark alarm as handled")
def handle_alarm(
    alarm_id_or_no: str,
    payload: AlarmHandleRequest,
    db: Session = Depends(get_db),
):
    alarm = inspection_alarm_service.mark_handled(db, alarm_id_or_no, payload.remark)
    if alarm is None:
        raise HTTPException(status_code=404, detail=f"alarm not found: {alarm_id_or_no}")
    return inspection_alarm_service.to_response(alarm)
