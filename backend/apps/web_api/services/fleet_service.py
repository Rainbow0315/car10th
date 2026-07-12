from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from common.config.settings import settings


ROBOT_TOPIC_PATTERN = re.compile(r"^robot/(?P<robot_code>[a-zA-Z0-9_-]{1,32})/(?P<message_type>[a-z_]+)$")


class FleetService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._robots: Dict[str, Dict[str, Any]] = {}
        self._commands: Dict[str, Dict[str, Any]] = {}
        self._formations: Dict[str, Dict[str, Any]] = {}

    def handle_robot_message(self, topic: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        parsed = self.parse_robot_topic(topic)
        if parsed is None:
            return None

        robot_code, message_type = parsed
        now = self._now()
        with self._lock:
            current = self._robots.get(robot_code) or self._empty_robot(robot_code, now)
            if message_type == "ack":
                previous_status = str(current.get("status") or "online")
                current["status"] = "online" if previous_status == "offline" else previous_status
            else:
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
            current["agent_hostname"] = payload.get("agent_hostname") or payload.get("hostname") or current.get("agent_hostname")
            current["agent_version"] = payload.get("agent_version") or current.get("agent_version")
            current["agent_ip"] = payload.get("agent_ip") or current.get("agent_ip")
            current["formation_id"] = payload.get("formation_id") or current.get("formation_id")
            current["formation_role"] = payload.get("formation_role") or current.get("formation_role")
            current["formation_slot"] = self._optional_int(payload.get("formation_slot"), current.get("formation_slot"))
            current["last_seen_at"] = now
            current["updated_at"] = now
            current["last_message_type"] = message_type
            current["payload"] = dict(payload)
            self._robots[robot_code] = current
            if message_type == "ack":
                self._record_command_ack(robot_code, payload, now)
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

    def create_command(
        self,
        robot_code: str,
        command: str,
        payload: Dict[str, Any],
        topic: str,
    ) -> Dict[str, Any]:
        now = self._now()
        command_id = uuid.uuid4().hex
        item = {
            "command_id": command_id,
            "robot_code": robot_code,
            "command": command,
            "payload": dict(payload),
            "topic": topic,
            "status": "pending",
            "issued_at": now,
            "published_at": None,
            "acked_at": None,
            "ack": None,
            "error": None,
        }
        with self._lock:
            self._commands[command_id] = item
        return dict(item)

    def mark_command_published(
        self,
        command_id: str,
        published: bool,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            current = self._commands[command_id]
            if published and current.get("status") == "acked":
                current["published_at"] = current.get("published_at") or self._now()
                return dict(current)
            current["status"] = "published" if published else "failed"
            current["published_at"] = self._now() if published else None
            current["error"] = error
            return dict(current)

    def get_command(self, command_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            current = self._commands.get(command_id)
            if current is None:
                return None
            self._with_command_timeout(current)
            return dict(current)

    def register_formation(
        self,
        formation_id: str,
        formation_type: str,
        mode: str,
        members: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        item = {
            "formation_id": formation_id,
            "formation_type": formation_type,
            "mode": mode,
            "created_at": self._now(),
            "members": [dict(member) for member in members],
        }
        with self._lock:
            self._formations[formation_id] = item
            return self._formation_snapshot(item)

    def list_formations(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._refresh_command_timeouts()
            return [self._formation_snapshot(item) for item in self._formations.values()]

    def get_formation(self, formation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            current = self._formations.get(formation_id)
            if current is None:
                return None
            self._refresh_command_timeouts()
            return self._formation_snapshot(current)

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            self._refresh_command_timeouts()
            robots = [self._with_liveness(dict(item)) for item in self._robots.values()]
            commands = list(self._commands.values())
            formations = [self._formation_snapshot(item) for item in self._formations.values()]

            robot_status_count = {
                "online": 0,
                "offline": 0,
                "error": 0,
            }
            for robot in robots:
                status = str(robot.get("status") or "offline")
                if status not in robot_status_count:
                    status = "error"
                robot_status_count[status] += 1

            command_status_count = {
                "pending": 0,
                "published": 0,
                "acked": 0,
                "failed": 0,
                "timeout": 0,
            }
            for command in commands:
                status = str(command.get("status") or "pending")
                if status not in command_status_count:
                    status = "failed"
                command_status_count[status] += 1

            return {
                "generated_at": self._now(),
                "total_robots": len(robots),
                "online_robots": robot_status_count["online"],
                "offline_robots": robot_status_count["offline"],
                "error_robots": robot_status_count["error"],
                "total_commands": len(commands),
                "pending_commands": command_status_count["pending"],
                "published_commands": command_status_count["published"],
                "acked_commands": command_status_count["acked"],
                "failed_commands": command_status_count["failed"],
                "timeout_commands": command_status_count["timeout"],
                "total_formations": len(formations),
                "ready_formations": sum(1 for item in formations if item.get("ready")),
            }

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
            "agent_hostname": None,
            "agent_version": None,
            "agent_ip": None,
            "formation_id": None,
            "formation_role": None,
            "formation_slot": None,
            "last_seen_at": None,
            "updated_at": now,
            "last_message_type": None,
            "payload": {},
        }

    def _record_command_ack(self, robot_code: str, payload: Dict[str, Any], now: datetime) -> None:
        command_id = str(payload.get("command_id") or "").strip()
        if not command_id:
            return
        current = self._commands.get(command_id)
        if current is None or current.get("robot_code") != robot_code:
            return
        ack_status = str(payload.get("status") or "acked").strip().lower()
        current["status"] = "acked" if ack_status in {"accepted", "acked", "ok", "done"} else "failed"
        current["acked_at"] = now
        current["ack"] = dict(payload)
        current["error"] = None if current["status"] == "acked" else payload.get("detail")

    def _refresh_command_timeouts(self) -> None:
        for command in self._commands.values():
            self._with_command_timeout(command)

    def _with_command_timeout(self, command: Dict[str, Any]) -> Dict[str, Any]:
        if command.get("status") != "published":
            return command

        published_at = command.get("published_at")
        if published_at is None:
            return command

        timeout_sec = max(1, settings.fleet_command_ack_timeout_sec)
        deadline = self._now() - timedelta(seconds=timeout_sec)
        if published_at < deadline:
            command["status"] = "timeout"
            command["error"] = f"ACK timeout after {timeout_sec}s"
        return command

    def _formation_snapshot(self, formation: Dict[str, Any]) -> Dict[str, Any]:
        members = []
        online_robots = 0
        acked_commands = 0
        for member in formation["members"]:
            robot_code = member["robot_code"]
            robot = self._with_liveness(dict(self._robots.get(robot_code) or self._empty_robot(robot_code, self._now())))
            command_current = self._commands.get(member["command_id"]) or {}
            self._with_command_timeout(command_current)
            command = dict(command_current)
            command_status = command.get("status")
            robot_ready = (
                robot.get("status") == "online"
                and command_status == "acked"
                and robot.get("formation_id") == formation["formation_id"]
                and robot.get("formation_role") == member["role"]
                and robot.get("formation_slot") == member["slot_index"]
            )
            if robot.get("status") == "online":
                online_robots += 1
            if command_status == "acked":
                acked_commands += 1
            members.append(
                {
                    "robot_code": robot_code,
                    "role": member["role"],
                    "slot_index": member["slot_index"],
                    "offset_x": member["offset_x"],
                    "offset_y": member["offset_y"],
                    "command": command,
                    "robot": robot,
                    "ready": robot_ready,
                }
            )

        total_robots = len(members)
        return {
            "formation_id": formation["formation_id"],
            "formation_type": formation["formation_type"],
            "mode": formation["mode"],
            "created_at": formation["created_at"],
            "total_robots": total_robots,
            "online_robots": online_robots,
            "acked_commands": acked_commands,
            "ready": total_robots > 0 and all(member["ready"] for member in members),
            "members": members,
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

    @staticmethod
    def _optional_int(value: Any, fallback: Optional[int]) -> Optional[int]:
        if value is None:
            return fallback
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback


fleet_service = FleetService()
