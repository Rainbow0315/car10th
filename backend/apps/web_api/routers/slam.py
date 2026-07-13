from __future__ import annotations

from fastapi import APIRouter

from apps.web_api.services.slam_service import slam_service
from common.schemas.slam import (
    SlamGoalRequest,
    SlamGoalResponse,
    SlamInitialPoseRequest,
    SlamInitialPoseResponse,
    SlamMapResponse,
)

router = APIRouter()


@router.get("/map", response_model=SlamMapResponse, summary="Get latest SLAM occupancy grid")
def get_slam_map():
    return slam_service.get_map()


@router.post("/goal", response_model=SlamGoalResponse, summary="Publish navigation goal")
def publish_nav_goal(payload: SlamGoalRequest):
    return slam_service.publish_goal(payload.model_dump())


@router.post("/initial-pose", response_model=SlamInitialPoseResponse, summary="Publish AMCL initial pose")
def publish_initial_pose(payload: SlamInitialPoseRequest):
    return slam_service.publish_initial_pose(payload.model_dump())
