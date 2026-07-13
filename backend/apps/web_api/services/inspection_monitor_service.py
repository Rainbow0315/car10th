from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from common.config.database import SessionLocal
from common.config.settings import settings
from common.schemas.inspection import InspectionMonitorStartRequest, InspectionMonitorStatusResponse

from .inspection_alarm_service import inspection_alarm_service
from .inspection_service import inspection_service

logger = logging.getLogger(__name__)


class InspectionMonitorService:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._config = InspectionMonitorStartRequest(
            topic_name=settings.inspection_monitor_topic,
            interval_sec=settings.inspection_monitor_interval_sec,
            timeout_sec=settings.inspection_monitor_timeout_sec,
            robot_code=settings.inspection_monitor_robot_code,
            camera_code=settings.inspection_monitor_camera_code,
            enabled_models=list(settings.default_enabled_models),
            output_dir=settings.inspection_monitor_output_dir,
        )
        self._started_at: Optional[datetime] = None
        self._last_checked_at: Optional[datetime] = None
        self._last_alarm_at: Optional[datetime] = None
        self._total_frames = 0
        self._total_alarm_frames = 0
        self._total_alarms = 0
        self._last_error: Optional[str] = None

    async def start(self, request: InspectionMonitorStartRequest) -> InspectionMonitorStatusResponse:
        async with self._lock:
            self._config = request
            if self._task is None or self._task.done():
                self._started_at = datetime.now()
                self._last_error = None
                self._task = asyncio.create_task(self._run_loop())
                logger.info("Inspection monitor started topic=%s", request.topic_name)
        return self.status()

    async def stop(self) -> InspectionMonitorStatusResponse:
        async with self._lock:
            if self._task is not None and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
            logger.info("Inspection monitor stopped")
        return self.status()

    async def shutdown(self) -> None:
        await self.stop()

    def status(self) -> InspectionMonitorStatusResponse:
        running = self._task is not None and not self._task.done()
        return InspectionMonitorStatusResponse(
            running=running,
            topic_name=self._config.topic_name,
            interval_sec=self._config.interval_sec,
            timeout_sec=self._config.timeout_sec,
            robot_code=self._config.robot_code,
            camera_code=self._config.camera_code,
            enabled_models=list(self._config.enabled_models),
            started_at=self._started_at if running else None,
            last_checked_at=self._last_checked_at,
            last_alarm_at=self._last_alarm_at,
            total_frames=self._total_frames,
            total_alarm_frames=self._total_alarm_frames,
            total_alarms=self._total_alarms,
            last_error=self._last_error,
        )

    async def inspect_once(self, request: InspectionMonitorStartRequest) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._inspect_once_sync, request)

    async def _run_loop(self) -> None:
        while True:
            started = datetime.now()
            try:
                await self.inspect_once(self._config)
                self._last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("Inspection monitor iteration failed")

            elapsed = (datetime.now() - started).total_seconds()
            await asyncio.sleep(max(0.0, self._config.interval_sec - elapsed))

    def _inspect_once_sync(self, request: InspectionMonitorStartRequest) -> Dict[str, Any]:
        payload = {
            "topic_name": request.topic_name,
            "timeout_sec": request.timeout_sec,
            "robot_code": request.robot_code,
            "camera_code": request.camera_code,
            "enabled_models": list(request.enabled_models),
            "output_dir": request.output_dir or settings.inspection_monitor_output_dir,
        }
        result = inspection_service.detect_ros_image(payload)
        self._last_checked_at = datetime.now()
        self._total_frames += 1

        summary = result.get("summary") or {}
        if not summary.get("has_risk"):
            self._delete_remote_frame(result)
            inspection_alarm_service.remove_non_risk_frame(result)
            return {"result": result, "alarms": []}

        self._download_risk_frame(result)
        with SessionLocal() as db:
            alarms = inspection_alarm_service.create_alarms_from_result(db, result, publish_mqtt=True)
        self._delete_remote_frame(result)

        if not alarms:
            return {"result": result, "alarms": []}

        self._total_alarm_frames += 1
        self._total_alarms += len(alarms)
        self._last_alarm_at = datetime.now()
        return {
            "result": result,
            "alarms": [inspection_alarm_service.to_response(alarm).model_dump(mode="json") for alarm in alarms],
        }

    def _download_risk_frame(self, result: Dict[str, Any]) -> None:
        if not settings.inspection_monitor_download_frames:
            return
        remote_path = str(result.get("image_path") or "")
        local_path = inspection_service.download_frame(remote_path, settings.inspection_monitor_local_frame_dir)
        if local_path:
            result["remote_image_path"] = remote_path
            result["image_path"] = local_path

    def _delete_remote_frame(self, result: Dict[str, Any]) -> None:
        if not settings.inspection_monitor_download_frames:
            return
        remote_path = str(result.get("remote_image_path") or result.get("image_path") or "")
        if remote_path:
            inspection_service.delete_frame(remote_path)


inspection_monitor_service = InspectionMonitorService()
