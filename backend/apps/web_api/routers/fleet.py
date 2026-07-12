from __future__ import annotations

from fastapi import APIRouter

from apps.web_api.services.fleet_service import fleet_service
from common.config.settings import settings
from common.schemas.fleet import FleetRobotListResponse, FleetRobotSnapshot

router = APIRouter()


@router.get("/robots", response_model=FleetRobotListResponse, summary="List fleet robots")
def list_fleet_robots():
    robots = [FleetRobotSnapshot.model_validate(item) for item in fleet_service.list_robots()]
    return FleetRobotListResponse(
        robots=robots,
        offline_after_sec=settings.fleet_robot_offline_sec,
    )


@router.get("/robots/{robot_code}", response_model=FleetRobotSnapshot, summary="Get fleet robot")
def get_fleet_robot(robot_code: str):
    return FleetRobotSnapshot.model_validate(fleet_service.get_robot(robot_code))
