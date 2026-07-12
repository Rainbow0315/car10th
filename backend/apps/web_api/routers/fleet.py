from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from apps.web_api.services.fleet_service import fleet_service
from common.config.settings import settings
from common.mqtt import fleet_command_topic, mqtt_manager
from common.schemas.fleet import (
    FleetBatchCommandRequest,
    FleetBatchCommandResponse,
    FleetCommandListResponse,
    FleetCommandRequest,
    FleetCommandSnapshot,
    FleetCommandStatus,
    FleetFormationListResponse,
    FleetFormationRequest,
    FleetFormationResponse,
    FleetFormationSnapshot,
    FleetReadinessRequest,
    FleetReadinessResponse,
    FleetRobotListResponse,
    FleetRobotSnapshot,
    FleetSummaryResponse,
)

router = APIRouter()


@router.get("/summary", response_model=FleetSummaryResponse, summary="Get fleet summary")
def get_fleet_summary():
    return FleetSummaryResponse.model_validate(fleet_service.get_summary())


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
    "/readiness",
    response_model=FleetReadinessResponse,
    summary="Check whether robots are ready for fleet commands",
)
def check_fleet_readiness(request: FleetReadinessRequest):
    robot_codes = _unique_robot_codes(request.robot_codes)
    if not robot_codes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="robot_codes must contain at least one non-empty robot code",
        )
    return FleetReadinessResponse.model_validate(fleet_service.check_readiness(robot_codes))


@router.post(
    "/robots/{robot_code}/commands",
    response_model=FleetCommandSnapshot,
    summary="Send command to one fleet robot",
)
def send_fleet_command(robot_code: str, request: FleetCommandRequest):
    command = _publish_fleet_command(robot_code, request.command, request.payload)
    if command["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=command["error"] or "MQTT publish failed",
        )
    return FleetCommandSnapshot.model_validate(command)


@router.post(
    "/commands/batch",
    response_model=FleetBatchCommandResponse,
    summary="Send one command to multiple fleet robots",
)
def send_batch_fleet_command(request: FleetBatchCommandRequest):
    robot_codes = _unique_robot_codes(request.robot_codes)
    if not robot_codes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="robot_codes must contain at least one non-empty robot code",
        )
    commands = [
        FleetCommandSnapshot.model_validate(
            _publish_fleet_command(robot_code, request.command, request.payload)
        )
        for robot_code in robot_codes
    ]
    return FleetBatchCommandResponse(commands=commands)


@router.post(
    "/formations",
    response_model=FleetFormationResponse,
    summary="Create a simple formation task for multiple robots",
)
def create_fleet_formation(request: FleetFormationRequest):
    robot_codes = _unique_robot_codes(request.robot_codes)
    if not robot_codes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="robot_codes must contain at least one non-empty robot code",
        )

    formation_id = uuid.uuid4().hex
    commands = []
    members = []
    for slot_index, robot_code in enumerate(robot_codes):
        role = "leader" if slot_index == 0 else "follower"
        payload = {
            "formation_id": formation_id,
            "formation_type": request.formation_type,
            "role": role,
            "slot_index": slot_index,
            "offset_x": -slot_index * request.spacing_m,
            "offset_y": 0.0,
            "mode": request.mode,
        }
        command = _publish_fleet_command(
            robot_code,
            "set_formation",
            payload,
        )
        commands.append(FleetCommandSnapshot.model_validate(command))
        members.append(
            {
                "robot_code": robot_code,
                "role": role,
                "slot_index": slot_index,
                "offset_x": payload["offset_x"],
                "offset_y": payload["offset_y"],
                "command_id": command["command_id"],
            }
        )
    fleet_service.register_formation(
        formation_id=formation_id,
        formation_type=request.formation_type,
        mode=request.mode,
        members=members,
    )
    return FleetFormationResponse(
        formation_id=formation_id,
        formation_type=request.formation_type,
        commands=commands,
    )


@router.get(
    "/formations",
    response_model=FleetFormationListResponse,
    summary="List fleet formations with readiness",
)
def list_fleet_formations():
    return FleetFormationListResponse(
        formations=[
            FleetFormationSnapshot.model_validate(item)
            for item in fleet_service.list_formations()
        ]
    )


@router.get(
    "/formations/{formation_id}",
    response_model=FleetFormationSnapshot,
    summary="Get fleet formation readiness",
)
def get_fleet_formation(formation_id: str):
    formation = fleet_service.get_formation(formation_id)
    if formation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="formation not found",
        )
    return FleetFormationSnapshot.model_validate(formation)


def _unique_robot_codes(robot_codes: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized = []
    for robot_code in robot_codes:
        item = robot_code.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _publish_fleet_command(
    robot_code: str,
    command_name: str,
    payload: dict,
):
    topic = fleet_command_topic(robot_code)
    command = fleet_service.create_command(
        robot_code=robot_code,
        command=command_name,
        payload=payload,
        topic=topic,
    )
    mqtt_payload = {
        "command_id": command["command_id"],
        "robot_code": robot_code,
        "command": command_name,
        "payload": payload,
        "issued_at": command["issued_at"].isoformat(),
    }
    published = mqtt_manager.publish_json(topic, mqtt_payload, qos=1, retain=False)
    command = fleet_service.mark_command_published(
        command["command_id"],
        published=published,
        error=None if published else mqtt_manager.last_error,
    )
    return command


@router.get(
    "/commands",
    response_model=FleetCommandListResponse,
    summary="List fleet commands with optional filters",
)
def list_fleet_commands(
    robot_code: str | None = Query(default=None, min_length=1, max_length=32),
    status_filter: FleetCommandStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
):
    commands = [
        FleetCommandSnapshot.model_validate(item)
        for item in fleet_service.list_commands(
            robot_code=robot_code,
            status=status_filter,
            limit=limit,
        )
    ]
    return FleetCommandListResponse(
        commands=commands,
        total=len(commands),
        limit=limit,
    )


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
