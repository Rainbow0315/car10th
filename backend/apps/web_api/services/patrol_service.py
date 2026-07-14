from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from apps.web_api.services.inspection_monitor_service import inspection_monitor_service
from apps.web_api.services.slam_service import slam_service
from apps.web_api.services.teleop_service import teleop_service
from common.config.database import SessionLocal
from common.config.settings import settings
from common.models import VideoAnalysisTask
from common.models.entities import TaskStatus, TriggerType
from common.schemas.inspection import InspectionMonitorStartRequest


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_waypoints(payload: Any) -> List[Dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    return []


@dataclass
class PatrolRuntimeState:
    task_code: str
    robot_code: str
    cancel_event: threading.Event
    thread: threading.Thread
    running: bool = True
    state: str = "running"
    current_seq: Optional[int] = None
    current_goal: Optional[Dict[str, Any]] = None
    last_pose: Optional[Dict[str, float]] = None
    message: Optional[str] = None
    detection_monitor_started: bool = False
    updated_at: datetime = _now()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "task_code": self.task_code,
            "running": self.running,
            "state": self.state,
            "robot_code": self.robot_code,
            "current_seq": self.current_seq,
            "current_goal": self.current_goal,
            "last_pose": self.last_pose,
            "message": self.message,
            "detection_monitor_started": self.detection_monitor_started,
            "updated_at": self.updated_at,
        }


class PatrolService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runtime: Dict[str, PatrolRuntimeState] = {}

        self.arrival_tolerance_m = float(0.35)
        self.arrival_hold_checks = int(2)
        self.poll_interval_sec = float(0.6)
        self.per_waypoint_timeout_sec = float(240.0)

    def list_tasks(self, limit: int = 50) -> List[VideoAnalysisTask]:
        with SessionLocal() as db:
            q = db.query(VideoAnalysisTask).order_by(VideoAnalysisTask.updated_at.desc()).limit(limit)
            return list(q.all())

    def get_task(self, task_code: str) -> VideoAnalysisTask:
        with SessionLocal() as db:
            task = db.query(VideoAnalysisTask).filter(VideoAnalysisTask.task_code == task_code).first()
            if task is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
            return task

    def create_task(self, payload: Dict[str, Any]) -> VideoAnalysisTask:
        task_code = uuid.uuid4().hex
        now = _now()
        with SessionLocal() as db:
            task = VideoAnalysisTask(
                task_code=task_code,
                task_name=str(payload["task_name"]),
                robot_code=str(payload.get("robot_code") or "robot_001"),
                camera_id=None,
                waypoints_json=_as_waypoints(payload.get("waypoints")),
                schedule_cron=payload.get("schedule_cron"),
                loop_count=int(payload.get("loop_count") or 1),
                return_to_start=1 if payload.get("return_to_start", True) else 0,
                detection_config=payload.get("detection_config"),
                status=TaskStatus.draft,
                trigger_type=TriggerType.app,
                started_at=None,
                finished_at=None,
                alarm_count=0,
                result_summary=None,
                error_message=None,
                created_by=None,
                created_at=now,
                updated_at=now,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return task

    def update_task(self, task_code: str, payload: Dict[str, Any]) -> VideoAnalysisTask:
        with SessionLocal() as db:
            task = db.query(VideoAnalysisTask).filter(VideoAnalysisTask.task_code == task_code).first()
            if task is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
            running = self._is_running_locked(task_code)
            if running:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务运行中，禁止修改")

            if payload.get("task_name") is not None:
                task.task_name = str(payload["task_name"])
            if payload.get("robot_code") is not None:
                task.robot_code = str(payload["robot_code"])
            if payload.get("waypoints") is not None:
                task.waypoints_json = _as_waypoints(payload.get("waypoints"))
            if payload.get("loop_count") is not None:
                task.loop_count = int(payload["loop_count"])
            if "schedule_cron" in payload:
                task.schedule_cron = payload.get("schedule_cron")
            if payload.get("return_to_start") is not None:
                task.return_to_start = 1 if bool(payload["return_to_start"]) else 0
            if "detection_config" in payload:
                task.detection_config = payload.get("detection_config")

            task.updated_at = _now()
            db.commit()
            db.refresh(task)
            return task

    def delete_task(self, task_code: str) -> None:
        running = self._is_running_locked(task_code)
        if running:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务运行中，禁止删除")
        with SessionLocal() as db:
            task = db.query(VideoAnalysisTask).filter(VideoAnalysisTask.task_code == task_code).first()
            if task is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
            db.delete(task)
            db.commit()

    def get_runtime(self, task_code: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            runtime = self._runtime.get(task_code)
            return None if runtime is None else runtime.snapshot()

    def start_task(self, task_code: str) -> None:
        task = self.get_task(task_code)
        waypoints = _as_waypoints(task.waypoints_json)
        if len(waypoints) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="航点不足 2 个")
        with self._lock:
            current = self._runtime.get(task_code)
            if current is not None and current.running:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务已在运行")
            for other in self._runtime.values():
                if other.running and other.robot_code == task.robot_code:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该机器人已有运行中的巡航任务")

            cancel_event = threading.Event()
            thread = threading.Thread(
                target=self._run_task,
                args=(task_code, task.robot_code, int(task.loop_count or 1), waypoints, cancel_event),
                daemon=True,
            )
            self._runtime[task_code] = PatrolRuntimeState(
                task_code=task_code,
                robot_code=task.robot_code,
                cancel_event=cancel_event,
                thread=thread,
                running=True,
                state="running",
                updated_at=_now(),
            )
            thread.start()

        self._start_detection_monitor(task)
        self._mark_db_running(task_code)

    def stop_task(self, task_code: str) -> None:
        runtime = None
        with self._lock:
            runtime = self._runtime.get(task_code)
            if runtime is None or not runtime.running:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务未运行")
            runtime.cancel_event.set()
            runtime.message = "cancel requested"
            runtime.updated_at = _now()
        try:
            teleop_service.stop()
        except HTTPException:
            pass
        self._stop_detection_monitor(task_code)
        self._mark_db_cancelled(task_code, "cancelled by user")

    def _is_running_locked(self, task_code: str) -> bool:
        with self._lock:
            runtime = self._runtime.get(task_code)
            return bool(runtime is not None and runtime.running)

    def _mark_db_running(self, task_code: str) -> None:
        with SessionLocal() as db:
            task = db.query(VideoAnalysisTask).filter(VideoAnalysisTask.task_code == task_code).first()
            if task is None:
                return
            task.status = TaskStatus.running
            task.trigger_type = TriggerType.app
            task.started_at = _now()
            task.finished_at = None
            task.error_message = None
            task.updated_at = _now()
            db.commit()

    def _mark_db_completed(self, task_code: str) -> None:
        with SessionLocal() as db:
            task = db.query(VideoAnalysisTask).filter(VideoAnalysisTask.task_code == task_code).first()
            if task is None:
                return
            task.status = TaskStatus.completed
            task.finished_at = _now()
            task.updated_at = _now()
            db.commit()

    def _mark_db_failed(self, task_code: str, error: str) -> None:
        with SessionLocal() as db:
            task = db.query(VideoAnalysisTask).filter(VideoAnalysisTask.task_code == task_code).first()
            if task is None:
                return
            task.status = TaskStatus.failed
            task.error_message = (error or "failed")[:512]
            task.finished_at = _now()
            task.updated_at = _now()
            db.commit()

    def _mark_db_cancelled(self, task_code: str, reason: str) -> None:
        with SessionLocal() as db:
            task = db.query(VideoAnalysisTask).filter(VideoAnalysisTask.task_code == task_code).first()
            if task is None:
                return
            task.status = TaskStatus.cancelled
            task.error_message = (reason or "cancelled")[:512]
            task.finished_at = _now()
            task.updated_at = _now()
            db.commit()

    def _update_runtime(self, task_code: str, **fields: Any) -> None:
        with self._lock:
            runtime = self._runtime.get(task_code)
            if runtime is None:
                return
            for k, v in fields.items():
                setattr(runtime, k, v)
            runtime.updated_at = _now()

    def _finish_runtime(self, task_code: str, state: str, message: str) -> None:
        with self._lock:
            runtime = self._runtime.get(task_code)
            if runtime is None:
                return
            runtime.running = False
            runtime.state = state
            runtime.message = message
            runtime.updated_at = _now()

    def _run_task(
        self,
        task_code: str,
        robot_code: str,
        loop_count: int,
        waypoints: List[Dict[str, Any]],
        cancel_event: threading.Event,
    ) -> None:
        try:
            for loop_idx in range(max(1, loop_count)):
                if cancel_event.is_set():
                    raise _Cancelled()
                for wp in waypoints:
                    if cancel_event.is_set():
                        raise _Cancelled()

                    seq = int(wp.get("seq") or 0) or None
                    self._update_runtime(task_code, current_seq=seq, current_goal=dict(wp), message=None)
                    slam_service.publish_goal(
                        {
                            "x": float(wp.get("x") or 0.0),
                            "y": float(wp.get("y") or 0.0),
                            "yaw": float(wp.get("yaw") or 0.0),
                            "frame_id": "map",
                        }
                    )
                    self._wait_until_arrived(task_code, wp, cancel_event)
                self._update_runtime(task_code, message=f"loop {loop_idx + 1}/{max(1, loop_count)} done")

            self._mark_db_completed(task_code)
            self._finish_runtime(task_code, "completed", "task completed")
        except _Cancelled:
            self._finish_runtime(task_code, "cancelled", "task cancelled")
        except Exception as exc:
            error = str(exc)[:512]
            self._mark_db_failed(task_code, error)
            self._finish_runtime(task_code, "failed", error)
        finally:
            self._stop_detection_monitor(task_code)

    def _start_detection_monitor(self, task: VideoAnalysisTask) -> None:
        config = task.detection_config if isinstance(task.detection_config, dict) else {}
        if config.get("enabled") is False:
            return

        status_snapshot = inspection_monitor_service.status()
        if status_snapshot.running:
            self._update_runtime(task.task_code, message="patrol running, existing detection monitor kept")
            return

        raw_models = config.get("enabled_models") or settings.default_enabled_models
        enabled_models = [raw_models] if isinstance(raw_models, str) else list(raw_models)
        request = InspectionMonitorStartRequest(
            topic_name=str(config.get("topic_name") or settings.inspection_monitor_topic),
            interval_sec=float(config.get("interval_sec") or settings.inspection_monitor_interval_sec),
            timeout_sec=float(config.get("timeout_sec") or settings.inspection_monitor_timeout_sec),
            robot_code=str(config.get("robot_code") or task.robot_code or settings.inspection_monitor_robot_code),
            camera_code=str(config.get("camera_code") or settings.inspection_monitor_camera_code),
            enabled_models=enabled_models,
            output_dir=str(config.get("output_dir") or settings.inspection_monitor_output_dir),
        )

        try:
            inspection_monitor_service.start_threadsafe(request)
            self._update_runtime(task.task_code, detection_monitor_started=True, message="patrol detection monitor started")
        except Exception as exc:
            self._update_runtime(task.task_code, message=f"detection monitor start failed: {str(exc)[:160]}")

    def _stop_detection_monitor(self, task_code: str) -> None:
        with self._lock:
            runtime = self._runtime.get(task_code)
            started = bool(runtime is not None and runtime.detection_monitor_started)
            if runtime is not None:
                runtime.detection_monitor_started = False
                runtime.updated_at = _now()
        if not started:
            return
        try:
            inspection_monitor_service.stop_threadsafe()
        except Exception as exc:
            self._update_runtime(task_code, message=f"detection monitor stop failed: {str(exc)[:160]}")

    def _wait_until_arrived(self, task_code: str, waypoint: Dict[str, Any], cancel_event: threading.Event) -> None:
        target_x = float(waypoint.get("x") or 0.0)
        target_y = float(waypoint.get("y") or 0.0)
        deadline = time.time() + self.per_waypoint_timeout_sec
        stable = 0
        last_distance = None

        while time.time() < deadline:
            if cancel_event.is_set():
                raise _Cancelled()
            snapshot = slam_service.get_map()
            pose = (snapshot.get("robot_pose") or None) if isinstance(snapshot, dict) else None
            if pose is None:
                stable = 0
                self._update_runtime(task_code, last_pose=None, message="waiting robot_pose")
                time.sleep(self.poll_interval_sec)
                continue

            current_x = float(pose.get("x") or 0.0)
            current_y = float(pose.get("y") or 0.0)
            distance = math.sqrt((current_x - target_x) ** 2 + (current_y - target_y) ** 2)
            last_distance = distance
            self._update_runtime(task_code, last_pose={"x": current_x, "y": current_y, "yaw": float(pose.get("yaw") or 0.0)})

            if distance <= self.arrival_tolerance_m:
                stable += 1
                if stable >= self.arrival_hold_checks:
                    return
            else:
                stable = 0

            time.sleep(self.poll_interval_sec)

        raise RuntimeError(f"waypoint timeout, last_distance={last_distance}")


class _Cancelled(Exception):
    pass


patrol_service = PatrolService()

