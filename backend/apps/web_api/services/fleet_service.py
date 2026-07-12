from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from common.config.settings import settings


ROBOT_TOPIC_PATTERN = re.compile(r"^robot/(?P<robot_code>[a-zA-Z0-9_-]{1,32})/(?P<message_type>[a-z_]+)$")


class FleetService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._robots: Dict[str, Dict[str, Any]] = {}

    def handle_robot_message(self, topic: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        parsed = self.parse_robot_topic(topic)
        if parsed is None:
            return None

        robot_code, message_type = parsed
        now = self._now()
        with self._lock:
            current = self._robots.get(robot_code) or self._empty_robot(robot_code, now)
            current["status"] = str(payload.get("status") or "online")
            current["mode"] = str(payload.get("mode") or current.get("mode") or "idle")
            current["battery"] = self._int_in_range(payload.get("battery"), current.get("battery", 0), 0, 100)
            current["network_latency"] = self._int_in_range(
                payload.get("network_latency"),
                current.get("network_latency", 0),
                0,
                999999,
            )
            current["pose_x"] = self._optional_float(payload.get("pose_x"), current.get("pose_x"))
            current["pose_y"] = self._optional_float(payload.get("pose_y"), current.get("pose_y"))
            current["pose_yaw"] = self._optional_float(payload.get("pose_yaw"), current.get("pose_yaw"))
            current["map_name"] = payload.get("map_name") or current.get("map_name")
            current["last_seen_at"] = now
            current["updated_at"] = now
            current["last_message_type"] = message_type
            current["payload"] = dict(payload)
            self._robots[robot_code] = current
            return dict(current)

    def list_robots(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._with_liveness(dict(item)) for item in self._robots.values()]

    def get_robot(self, robot_code: str) -> Dict[str, Any]:
        with self._lock:
            current = self._robots.get(robot_code)
            if current is None:
                return self._with_liveness(self._empty_robot(robot_code, self._now()))
            return self._with_liveness(dict(current))

    def parse_robot_topic(self, topic: str) -> Optional[tuple[str, str]]:
        match = ROBOT_TOPIC_PATTERN.match(topic)
        if match is None:
            return None
        return match.group("robot_code"), match.group("message_type")

    def _with_liveness(self, robot: Dict[str, Any]) -> Dict[str, Any]:
        last_seen_at = robot.get("last_seen_at")
        if last_seen_at is None:
            robot["status"] = "offline"
            return robot

        deadline = self._now() - timedelta(seconds=max(1, settings.fleet_robot_offline_sec))
        if last_seen_at < deadline:
            robot["status"] = "offline"
        return robot

    def _empty_robot(self, robot_code: str, now: datetime) -> Dict[str, Any]:
        return {
            "robot_code": robot_code,
            "status": "offline",
            "mode": "idle",
            "battery": 0,
            "network_latency": 0,
            "pose_x": None,
            "pose_y": None,
            "pose_yaw": None,
            "map_name": None,
            "last_seen_at": None,
            "updated_at": now,
            "last_message_type": None,
            "payload": {},
        }

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _int_in_range(value: Any, fallback: int, lower: int, upper: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(fallback)
        return max(lower, min(upper, parsed))

    @staticmethod
    def _optional_float(value: Any, fallback: Optional[float]) -> Optional[float]:
        if value is None:
            return fallback
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback


fleet_service = FleetService()
