from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException

from apps.ai_service.pipelines.inspection import inspection_pipeline
from common.schemas.inspection import ImageInspectionRequest, ImageInspectionResponse

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


@app.post("/api/inspection/detect-plate", response_model=ImageInspectionResponse)
def detect_plate(payload: ImageInspectionRequest):
    """车牌检测 + OCR 识别"""
    payload.enabled_models = ["plate"]
    try:
        return inspection_pipeline.inspect_image(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(
        "apps.ai_service.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
    )
