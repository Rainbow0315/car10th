from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from apps.web_api.services.teleop_service import teleop_service

logger = logging.getLogger(__name__)

ROBOT_CODE_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


class RobotService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._status_cache: Dict[str, Dict[str, Any]] = {}
        self._ensure_default_robot("robot_001")

    def _ensure_default_robot(self, robot_code: str) -> None:
        if robot_code not in self._status_cache:
            now = self._now()
            self._status_cache[robot_code] = {
                "robot_code": robot_code,
                "status": "offline",
                "mode": "idle",
                "battery": 0,
                "network_latency": 0,
                "pose_x": None,
                "pose_y": None,
                "pose_yaw": None,
                "map_name": None,
                "updated_at": now,
            }

    def list_status(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._status_cache.values())

    def get_status(self, robot_code: str) -> Dict[str, Any]:
        self._validate_robot_code(robot_code)
        with self._lock:
            self._ensure_default_robot(robot_code)
            return dict(self._status_cache[robot_code])

    def update_status(self, robot_code: str, **fields: Any) -> Dict[str, Any]:
        self._validate_robot_code(robot_code)
        with self._lock:
            self._ensure_default_robot(robot_code)
            current = self._status_cache[robot_code]
            current.update(fields)
            current["updated_at"] = self._now()
            return dict(current)

    def mark_online(self, robot_code: str, mode: str = "idle") -> Dict[str, Any]:
        return self.update_status(robot_code, status="online", mode=mode)

    def dispatch_control(self, robot_code: str, command: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._validate_robot_code(robot_code)
        command = command.strip().lower()

        if command == "cmd_vel":
            result = teleop_service.publish_cmd_vel(payload)
            self.update_status(robot_code, status="online", mode="teleop")
            return {
                "robot_code": robot_code,
                "command": command,
                "status": "accepted",
                "result": result,
            }

        if command == "stop":
            result = teleop_service.stop()
            self.update_status(robot_code, status="online", mode="idle")
            return {
                "robot_code": robot_code,
                "command": command,
                "status": "accepted",
                "result": result,
            }

        if command in {"patrol_start", "patrol_stop", "mode_follow"}:
            mode_map = {
                "patrol_start": "patrol",
                "patrol_stop": "idle",
                "mode_follow": "follow",
            }
            self.update_status(robot_code, status="online", mode=mode_map[command])
            return {
                "robot_code": robot_code,
                "command": command,
                "status": "accepted",
                "detail": "指令已接收，巡检/跟随逻辑将在 patrol_task 模块实现",
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的指令: {command}",
        )

    def parse_control_topic(self, topic: str) -> Optional[str]:
        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != "app" or parts[1] != "control":
            return None
        robot_code = parts[2]
        if not ROBOT_CODE_PATTERN.match(robot_code):
            return None
        return robot_code

    def _validate_robot_code(self, robot_code: str) -> None:
        if not ROBOT_CODE_PATTERN.match(robot_code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的 robot_code")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)


robot_service = RobotService()
