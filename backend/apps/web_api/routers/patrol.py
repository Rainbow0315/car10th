from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from apps.web_api.services.patrol_service import patrol_service
from common.schemas.patrol import (
    PatrolRuntimePayload,
    PatrolTaskCreateRequest,
    PatrolTaskListResponse,
    PatrolTaskPayload,
    PatrolTaskStartResponse,
    PatrolTaskStopResponse,
    PatrolTaskUpdateRequest,
    PatrolWaypoint,
)

router = APIRouter()


def _as_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.min


def _task_to_payload(task: Any) -> PatrolTaskPayload:
    waypoints: List[PatrolWaypoint] = []
    for raw in (task.waypoints_json or []):
        if not isinstance(raw, dict):
            continue
        waypoints.append(
            PatrolWaypoint(
                seq=int(raw.get("seq") or 0),
                x=float(raw.get("x") or 0.0),
                y=float(raw.get("y") or 0.0),
                yaw=float(raw.get("yaw") or 0.0),
                name=str(raw.get("name") or ""),
            )
        )
    waypoints.sort(key=lambda w: w.seq)
    return PatrolTaskPayload(
        task_code=str(task.task_code),
        task_name=str(task.task_name),
        robot_code=str(task.robot_code),
        waypoints=waypoints,
        schedule_cron=task.schedule_cron,
        loop_count=int(task.loop_count or 1),
        return_to_start=bool(int(task.return_to_start or 0)),
        status=str(task.status.value if getattr(task.status, "value", None) else task.status),
        trigger_type=str(task.trigger_type.value if getattr(task.trigger_type, "value", None) else task.trigger_type),
        started_at=task.started_at,
        finished_at=task.finished_at,
        error_message=task.error_message,
        created_at=_as_dt(task.created_at),
        updated_at=_as_dt(task.updated_at),
    )


@router.get("/tasks", response_model=PatrolTaskListResponse, summary="List patrol tasks")
def list_tasks(limit: int = Query(50, ge=1, le=200)):
    items = [_task_to_payload(task) for task in patrol_service.list_tasks(limit=limit)]
    return PatrolTaskListResponse(items=items)


@router.post("/tasks", response_model=PatrolTaskPayload, summary="Create patrol task")
def create_task(payload: PatrolTaskCreateRequest):
    task = patrol_service.create_task(
        {
            "task_name": payload.task_name,
            "robot_code": payload.robot_code,
            "waypoints": [wp.model_dump() for wp in payload.waypoints],
            "loop_count": payload.loop_count,
            "schedule_cron": payload.schedule_cron,
            "return_to_start": payload.return_to_start,
            "detection_config": payload.detection_config,
        }
    )
    return _task_to_payload(task)


@router.get("/tasks/{task_code}", response_model=PatrolTaskPayload, summary="Get patrol task")
def get_task(task_code: str):
    task = patrol_service.get_task(task_code)
    return _task_to_payload(task)


@router.put("/tasks/{task_code}", response_model=PatrolTaskPayload, summary="Update patrol task")
def update_task(task_code: str, payload: PatrolTaskUpdateRequest):
    update_payload: Dict[str, Any] = payload.model_dump(exclude_unset=True)
    if update_payload.get("waypoints") is not None:
        update_payload["waypoints"] = [PatrolWaypoint(**wp).model_dump() for wp in update_payload["waypoints"]]
    task = patrol_service.update_task(task_code, update_payload)
    return _task_to_payload(task)


@router.delete("/tasks/{task_code}", summary="Delete patrol task")
def delete_task(task_code: str):
    patrol_service.delete_task(task_code)
    return {"status": "ok", "task_code": task_code}


@router.post("/tasks/{task_code}/start", response_model=PatrolTaskStartResponse, summary="Start patrol task")
def start_task(task_code: str):
    patrol_service.start_task(task_code)
    return PatrolTaskStartResponse(task_code=task_code, status="accepted", detail="patrol started")


@router.post("/tasks/{task_code}/stop", response_model=PatrolTaskStopResponse, summary="Stop patrol task")
def stop_task(task_code: str):
    patrol_service.stop_task(task_code)
    return PatrolTaskStopResponse(task_code=task_code, status="accepted", detail="patrol stop requested")


@router.get("/tasks/{task_code}/runtime", response_model=Optional[PatrolRuntimePayload], summary="Get patrol runtime")
def get_runtime(task_code: str):
    runtime = patrol_service.get_runtime(task_code)
    if runtime is None:
        return None
    return PatrolRuntimePayload(**runtime)

