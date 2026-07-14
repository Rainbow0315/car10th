from __future__ import annotations

from fastapi import APIRouter

from apps.web_api.services.car_finding_service import car_finding_service
from common.schemas.car_finding import (
    BindPlateRequest,
    GuideToSpotOneRequest,
    GuideToSpotOneResponse,
    ParkingRecordResponse,
    ParkingSpotListResponse,
    ParkAtSpotOneRequest,
    PlateBindingResponse,
    VerifyAtSpotOneRequest,
    VerifyAtSpotOneResponse,
)

router = APIRouter()


@router.get("/parking-spots", response_model=ParkingSpotListResponse, summary="List fixed parking spots")
def list_parking_spots():
    return {"spots": car_finding_service.parking_spots()}


@router.post("/bind-plate", response_model=PlateBindingResponse, summary="Bind a user's plate number")
def bind_plate(payload: BindPlateRequest):
    return car_finding_service.bind_plate(payload.user_id, payload.plate_number)


@router.post("/park-at-spot-one", response_model=ParkingRecordResponse, summary="Record the user's car at spot one")
def park_at_spot_one(payload: ParkAtSpotOneRequest):
    return car_finding_service.park_at_spot_one(payload.user_id, payload.plate_number)


@router.post("/guide-to-spot-one", response_model=GuideToSpotOneResponse, summary="Navigate robot to spot one")
def guide_to_spot_one(payload: GuideToSpotOneRequest):
    return car_finding_service.guide_to_spot_one(payload.user_id)


@router.post("/verify-at-spot-one", response_model=VerifyAtSpotOneResponse, summary="Detect and compare plate at spot one")
def verify_at_spot_one(payload: VerifyAtSpotOneRequest):
    return car_finding_service.verify_at_spot_one(
        user_id=payload.user_id,
        topic_name=payload.topic_name,
        timeout_sec=payload.timeout_sec,
        robot_code=payload.robot_code,
        camera_code=payload.camera_code,
    )
