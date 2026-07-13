from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse

from apps.ai_service.pipelines.inspection import inspection_pipeline
from apps.ai_service.ros_image_capture import ros_image_capture_service
from common.schemas.inspection import ImageInspectionRequest, ImageInspectionResponse, RosTopicInspectionRequest

app = FastAPI(
    title="Road Inspection AI Service",
    description="道路裂缝 / 积水 / 异物检测服务",
    version="0.1.0",
)


@app.on_event("shutdown")
def shutdown_ros_image_cache():
    ros_image_capture_service.shutdown()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ai_service"}


@app.post("/api/inspection/detect-image", response_model=ImageInspectionResponse)
def detect_image(payload: ImageInspectionRequest):
    try:
        return inspection_pipeline.inspect_image(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/inspection/detect-ros-image", response_model=ImageInspectionResponse)
def detect_ros_image(payload: RosTopicInspectionRequest):
    try:
        return inspection_pipeline.inspect_ros_topic(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/inspection/frame")
def get_frame(image_path: str = Query(...)):
    path = _resolve_frame_path(image_path)
    return FileResponse(path)


@app.delete("/api/inspection/frame")
def delete_frame(image_path: str = Query(...)):
    path = _resolve_frame_path(image_path)
    path.unlink(missing_ok=True)
    return {"deleted": True, "image_path": str(path)}


@app.get("/api/camera/snapshot")
def camera_snapshot(
    topic_name: str = Query("/image_raw", description="ROS image topic"),
    timeout_sec: float = Query(3.0, ge=0.5, le=10.0, description="Frame wait timeout in seconds"),
):
    try:
        jpeg, metadata = ros_image_capture_service.latest_jpeg(
            topic_name=topic_name,
            timeout_sec=timeout_sec,
            node_name="ai_service_camera_snapshot",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Camera-Topic": metadata["topic_name"],
            "X-Camera-Frame-Width": metadata["width"],
            "X-Camera-Frame-Height": metadata["height"],
            "X-Camera-Frame-Received-At": metadata["received_at"],
        },
    )


@app.get("/api/camera/status")
def camera_status():
    return ros_image_capture_service.status()


@app.get("/api/camera/mjpeg")
def camera_mjpeg(
    topic_name: str = Query("/image_raw", description="ROS image topic"),
    fps: float = Query(5.0, ge=0.5, le=10.0, description="MJPEG frame rate"),
    timeout_sec: float = Query(3.0, ge=0.5, le=10.0, description="Frame wait timeout in seconds"),
):
    boundary = "frame"

    def stream() -> Iterator[bytes]:
        interval = 1.0 / max(0.5, fps)
        while True:
            start = time.monotonic()
            try:
                jpeg, _ = ros_image_capture_service.latest_jpeg(
                    topic_name=topic_name,
                    timeout_sec=timeout_sec,
                    node_name="ai_service_camera_mjpeg",
                )
            except RuntimeError:
                time.sleep(min(interval, 0.5))
                continue
            yield (
                f"--{boundary}\r\n"
                "Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(jpeg)}\r\n"
                "Cache-Control: no-store\r\n"
                "\r\n"
            ).encode("ascii")
            yield jpeg
            yield b"\r\n"
            elapsed = time.monotonic() - start
            if elapsed < interval:
                time.sleep(interval - elapsed)

    return StreamingResponse(
        stream(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={"Cache-Control": "no-store"},
    )


def _resolve_frame_path(image_path: str) -> Path:
    path = Path(image_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"frame not found: {image_path}")
    return path


if __name__ == "__main__":
    uvicorn.run(
        "apps.ai_service.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
    )
