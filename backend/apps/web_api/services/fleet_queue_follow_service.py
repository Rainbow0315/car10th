from __future__ import annotations

import math
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Optional

from apps.web_api.services.fleet_service import fleet_service
from apps.web_api.services.fleet_teleop_service import send_cmd_vel_to_ros_bridges, stop_ros_bridges
from common.config.settings import settings


class FleetQueueFollowService:
    """Centralized queue-follow controller.

    The leader keeps using the existing car-side person-following capability.
    This service only sends conservative /cmd_vel commands to followers.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[Dict[str, Any]] = None
        self._histories: Dict[str, Deque[Dict[str, Any]]] = {}

    def start(
        self,
        *,
        robot_codes: list[str],
        leader_robot_code: Optional[str],
        spacing_m: float,
        target_lag_sec: float,
        interval_sec: float,
        max_linear_x: float,
        max_angular_z: float,
    ) -> Dict[str, Any]:
        ordered = self._ordered_robot_codes(robot_codes, leader_robot_code)
        if len(ordered) < 2:
            raise ValueError("queue follow requires at least two robots")

        self.stop(stop_motion=True)

        now = self._now()
        session_id = uuid.uuid4().hex
        members = []
        for index, robot_code in enumerate(ordered):
            members.append(
                {
                    "robot_code": robot_code,
                    "role": "leader" if index == 0 else "follower",
                    "target_robot_code": None if index == 0 else ordered[index - 1],
                    "target_lag_sec": target_lag_sec,
                    "spacing_m": spacing_m,
                    "last_command": None,
                    "last_error": None,
                }
            )

        stop_event = threading.Event()
        session = {
            "active": True,
            "session_id": session_id,
            "leader_robot_code": ordered[0],
            "robot_codes": ordered,
            "started_at": now,
            "updated_at": now,
            "loop_count": 0,
            "pose_max_age_sec": settings.fleet_queue_follow_pose_max_age_sec,
            "interval_sec": interval_sec,
            "max_linear_x": max_linear_x,
            "max_angular_z": max_angular_z,
            "members": members,
        }
        with self._lock:
            self._session = session
            self._histories = {robot_code: deque(maxlen=120) for robot_code in ordered}
            self._stop_event = stop_event
            self._thread = threading.Thread(
                target=self._run_loop,
                args=(session_id, stop_event),
                name=f"fleet-queue-follow-{session_id[:8]}",
                daemon=True,
            )
            self._thread.start()
        return self.status()

    def stop(self, *, stop_motion: bool = True) -> Dict[str, Any]:
        with self._lock:
            session = self._session
            stop_event = self._stop_event
            thread = self._thread
            follower_codes = [
                member["robot_code"]
                for member in (session or {}).get("members", [])
                if member.get("role") == "follower"
            ]
            if session is not None:
                session["active"] = False
                session["updated_at"] = self._now()
            self._session = None
            self._stop_event = None
            self._thread = None
            self._histories = {}

        if stop_event is not None:
            stop_event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        if stop_motion and follower_codes:
            stop_ros_bridges(follower_codes)
        return self._snapshot(session, active=False) if session is not None else self.status()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot(self._session, active=bool(self._session and self._session.get("active")))

    def _run_loop(self, session_id: str, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            with self._lock:
                session = self._session
                if session is None or session.get("session_id") != session_id or not session.get("active"):
                    return
                interval_sec = float(session["interval_sec"])
            try:
                self._tick(session_id)
            except Exception as exc:
                self._mark_all_followers_error(session_id, str(exc))
            stop_event.wait(interval_sec)

    def _tick(self, session_id: str) -> None:
        with self._lock:
            session = self._session
            if session is None or session.get("session_id") != session_id:
                return
            robot_codes = list(session["robot_codes"])
            members = [dict(member) for member in session["members"]]
            pose_max_age_sec = float(session["pose_max_age_sec"])
            interval_sec = float(session["interval_sec"])
            target_lag_sec = float(members[1]["target_lag_sec"]) if len(members) > 1 else 0.0
            max_linear_x = float(session["max_linear_x"])
            max_angular_z = float(session["max_angular_z"])

        now_monotonic = time.monotonic()
        poses = {robot_code: self._fresh_pose(robot_code, pose_max_age_sec) for robot_code in robot_codes}
        with self._lock:
            if self._session is None or self._session.get("session_id") != session_id:
                return
            for robot_code, pose in poses.items():
                if pose is not None:
                    self._histories.setdefault(robot_code, deque(maxlen=120)).append(
                        {"monotonic": now_monotonic, **pose}
                    )

        for member in members:
            if member["role"] != "follower":
                continue
            follower_code = str(member["robot_code"])
            target_code = str(member["target_robot_code"])
            follower_pose = poses.get(follower_code)
            if follower_pose is None:
                self._stop_follower(session_id, follower_code, "follower pose unavailable or stale")
                continue
            target_pose = self._target_pose(target_code, now_monotonic - target_lag_sec)
            if target_pose is None:
                self._stop_follower(session_id, follower_code, f"target pose unavailable for {target_code}")
                continue
            command = self._motion_to_target(
                follower_pose=follower_pose,
                target_pose=target_pose,
                spacing_m=float(member["spacing_m"]),
                max_linear_x=max_linear_x,
                max_angular_z=max_angular_z,
            )
            result = send_cmd_vel_to_ros_bridges(
                [follower_code],
                linear_x=command["linear_x"],
                linear_y=0.0,
                angular_z=command["angular_z"],
                duration=max(0.2, min(1.0, interval_sec)),
                rate_hz=10.0,
                wait_for_subscriber_timeout=0.2,
            )
            command["target_robot_code"] = target_code
            command["target_x"] = target_pose["x"]
            command["target_y"] = target_pose["y"]
            command["distance_m"] = round(command["distance_m"], 3)
            self._update_member(session_id, follower_code, last_command={**command, "teleop": result}, last_error=None)

        with self._lock:
            if self._session is not None and self._session.get("session_id") == session_id:
                self._session["loop_count"] = int(self._session.get("loop_count") or 0) + 1
                self._session["updated_at"] = self._now()

    def _fresh_pose(self, robot_code: str, max_age_sec: float) -> Optional[Dict[str, float]]:
        robot = fleet_service.get_robot(robot_code)
        pose_updated_at = robot.get("pose_updated_at")
        if pose_updated_at is None:
            return None
        if isinstance(pose_updated_at, str):
            try:
                pose_updated_at = datetime.fromisoformat(pose_updated_at)
            except ValueError:
                return None
        if self._now() - pose_updated_at > timedelta(seconds=max_age_sec):
            return None
        try:
            return {
                "x": float(robot["pose_x"]),
                "y": float(robot["pose_y"]),
                "yaw": float(robot.get("pose_yaw") or 0.0),
            }
        except (TypeError, ValueError):
            return None

    def _target_pose(self, robot_code: str, target_monotonic: float) -> Optional[Dict[str, float]]:
        with self._lock:
            history = list(self._histories.get(robot_code) or [])
        if not history:
            return None
        candidates = [item for item in history if item["monotonic"] <= target_monotonic]
        pose = candidates[-1] if candidates else history[0]
        return {"x": float(pose["x"]), "y": float(pose["y"]), "yaw": float(pose.get("yaw") or 0.0)}

    def _motion_to_target(
        self,
        *,
        follower_pose: Dict[str, float],
        target_pose: Dict[str, float],
        spacing_m: float,
        max_linear_x: float,
        max_angular_z: float,
    ) -> Dict[str, float]:
        desired_x = target_pose["x"] - spacing_m * math.cos(target_pose["yaw"])
        desired_y = target_pose["y"] - spacing_m * math.sin(target_pose["yaw"])
        dx = desired_x - follower_pose["x"]
        dy = desired_y - follower_pose["y"]
        distance = math.hypot(dx, dy)
        heading = math.atan2(dy, dx)
        heading_error = _normalize_angle(heading - follower_pose["yaw"])

        if distance < 0.08:
            return {"linear_x": 0.0, "angular_z": 0.0, "distance_m": distance, "heading_error_rad": heading_error}

        angular_z = _clamp(heading_error * 0.9, -max_angular_z, max_angular_z)
        linear_x = _clamp(distance * 0.45, 0.0, max_linear_x)
        if abs(heading_error) > 1.0:
            linear_x = 0.0
        return {
            "linear_x": round(linear_x, 4),
            "angular_z": round(angular_z, 4),
            "distance_m": distance,
            "heading_error_rad": round(heading_error, 4),
        }

    def _stop_follower(self, session_id: str, robot_code: str, reason: str) -> None:
        stop_ros_bridges([robot_code])
        self._update_member(session_id, robot_code, last_command={"linear_x": 0.0, "angular_z": 0.0}, last_error=reason)

    def _update_member(
        self,
        session_id: str,
        robot_code: str,
        *,
        last_command: Dict[str, Any],
        last_error: Optional[str],
    ) -> None:
        with self._lock:
            session = self._session
            if session is None or session.get("session_id") != session_id:
                return
            for member in session["members"]:
                if member["robot_code"] == robot_code:
                    member["last_command"] = last_command
                    member["last_error"] = last_error
                    break
            session["updated_at"] = self._now()

    def _mark_all_followers_error(self, session_id: str, error: str) -> None:
        with self._lock:
            session = self._session
            if session is None or session.get("session_id") != session_id:
                return
            for member in session["members"]:
                if member["role"] == "follower":
                    member["last_error"] = error
            session["updated_at"] = self._now()

    def _snapshot(self, session: Optional[Dict[str, Any]], *, active: bool) -> Dict[str, Any]:
        if session is None:
            return {
                "active": False,
                "session_id": None,
                "leader_robot_code": None,
                "robot_codes": [],
                "started_at": None,
                "updated_at": None,
                "loop_count": 0,
                "pose_max_age_sec": settings.fleet_queue_follow_pose_max_age_sec,
                "members": [],
            }
        return {
            "active": active,
            "session_id": session.get("session_id"),
            "leader_robot_code": session.get("leader_robot_code"),
            "robot_codes": list(session.get("robot_codes") or []),
            "started_at": session.get("started_at"),
            "updated_at": session.get("updated_at"),
            "loop_count": int(session.get("loop_count") or 0),
            "pose_max_age_sec": float(session.get("pose_max_age_sec") or settings.fleet_queue_follow_pose_max_age_sec),
            "interval_sec": float(session.get("interval_sec") or settings.fleet_queue_follow_interval_sec),
            "members": [dict(member) for member in session.get("members") or []],
        }

    @staticmethod
    def _ordered_robot_codes(robot_codes: list[str], leader_robot_code: Optional[str]) -> list[str]:
        seen: set[str] = set()
        cleaned = []
        for robot_code in robot_codes:
            item = robot_code.strip()
            if item and item not in seen:
                seen.add(item)
                cleaned.append(item)
        leader = (leader_robot_code or (cleaned[0] if cleaned else "")).strip()
        if leader and leader in cleaned:
            return [leader, *[code for code in cleaned if code != leader]]
        return cleaned

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_angle(value: float) -> float:
    return math.atan2(math.sin(value), math.cos(value))


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


fleet_queue_follow_service = FleetQueueFollowService()
