from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from apps.web_api.services.fleet_service import fleet_service
from common.config.settings import settings
from common.mqtt import fleet_command_topic, mqtt_manager
from common.schemas.fleet import (
    FleetCommandRequest,
    FleetCommandSnapshot,
    FleetRobotListResponse,
    FleetRobotSnapshot,
)

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


@router.post(
    "/robots/{robot_code}/commands",
    response_model=FleetCommandSnapshot,
    summary="Send command to one fleet robot",
)
def send_fleet_command(robot_code: str, request: FleetCommandRequest):
    topic = fleet_command_topic(robot_code)
    command = fleet_service.create_command(
        robot_code=robot_code,
        command=request.command,
        payload=request.payload,
        topic=topic,
    )
    mqtt_payload = {
        "command_id": command["command_id"],
        "robot_code": robot_code,
        "command": request.command,
        "payload": request.payload,
        "issued_at": command["issued_at"].isoformat(),
    }
    published = mqtt_manager.publish_json(topic, mqtt_payload, qos=1, retain=False)
    command = fleet_service.mark_command_published(
        command["command_id"],
        published=published,
        error=None if published else mqtt_manager.last_error,
    )
    if not published:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=command["error"] or "MQTT publish failed",
        )
    return FleetCommandSnapshot.model_validate(command)


@router.get(
    "/commands/{command_id}",
    response_model=FleetCommandSnapshot,
    summary="Get fleet command ACK status",
)
def get_fleet_command(command_id: str):
    command = fleet_service.get_command(command_id)
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="command not found")
    return FleetCommandSnapshot.model_validate(command)
