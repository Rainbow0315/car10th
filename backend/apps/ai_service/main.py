from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from apps.ai_service.pipelines.inspection import inspection_pipeline
from common.schemas.inspection import ImageInspectionRequest, ImageInspectionResponse, RosTopicInspectionRequest

app = FastAPI(
    title="Road Inspection AI Service",
    description="道路裂缝 / 积水 / 异物检测服务",
    version="0.1.0",
)


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
