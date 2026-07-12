from __future__ import annotations

from fastapi import APIRouter

from apps.web_api.services.inspection_service import inspection_service
from common.schemas.inspection import ImageInspectionRequest, ImageInspectionResponse

router = APIRouter()


@router.get("/health", summary="AI service health")
def inspection_health():
    return inspection_service.health()


@router.post("/detect-image", response_model=ImageInspectionResponse, summary="Run road inspection on one image")
def detect_image(payload: ImageInspectionRequest):
    return inspection_service.detect_image(payload.model_dump())
