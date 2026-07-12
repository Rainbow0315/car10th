from __future__ import annotations

import argparse
import json
import signal
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any, Dict

import httpx
import paho.mqtt.client as mqtt

from common.config.settings import settings
from common.mqtt import robot_ack_topic, robot_heartbeat_topic, robot_status_up_topic


class RobotAgent:
    def __init__(self, robot_code: str, interval_sec: int, dry_run: bool) -> None:
        self.robot_code = robot_code
        self.interval_sec = max(1, interval_sec)
        self.dry_run = dry_run
        self.mode = "idle"
        self.formation_id: str | None = None
        self.formation_role: str | None = None
        self.formation_slot: int | None = None
        self.rescue_incident_id: str | None = None
        self.rescue_target_robot_code: str | None = None
        self.escort_mission_id: str | None = None
        self.escort_target_robot_code: str | None = None
        self.hostname = socket.gethostname()
        self.agent_version = self._load_deployed_commit()
        self.stop_event = Event()
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{robot_code}_agent",
            clean_session=True,
        )
        username = settings.mqtt_robot_username or settings.mqtt_username
        password = settings.mqtt_robot_password or settings.mqtt_password
        if username:
            self.client.username_pw_set(username, password or None)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)

    def run(self) -> None:
        self.client.connect(
            settings.mqtt_broker_host,
            settings.mqtt_broker_port,
            keepalive=settings.mqtt_keepalive,
        )
        self.client.loop_start()
        print(
            f"robot_agent started: robot_code={self.robot_code}, "
            f"broker={settings.mqtt_broker_host}:{settings.mqtt_broker_port}, dry_run={self.dry_run}"
        )
        try:
            while not self.stop_event.is_set():
                self.publish_heartbeat()
                self.publish_status()
                self.stop_event.wait(self.interval_sec)
        finally:
            self.publish_status(status="offline", mode="idle")
            self.client.loop_stop()
            self.client.disconnect()

    def publish_heartbeat(self) -> None:
        self._publish(
            robot_heartbeat_topic(self.robot_code),
            {
                "robot_code": self.robot_code,
                "status": "online",
                "hostname": self.hostname,
                "agent_version": self.agent_version,
                "agent_ip": self._local_ip(),
                "timestamp": self._now_iso(),
            },
        )

    def publish_status(self, status: str = "online", mode: str | None = None) -> None:
        self._publish(
            robot_status_up_topic(self.robot_code),
            {
                "robot_code": self.robot_code,
                "status": status,
                "mode": mode or self.mode,
                "battery": 100 if self.dry_run else 0,
                "network_latency": 0,
                "agent_hostname": self.hostname,
                "agent_version": self.agent_version,
                "agent_ip": self._local_ip(),
                "formation_id": self.formation_id,
                "formation_role": self.formation_role,
                "formation_slot": self.formation_slot,
                "rescue_incident_id": self.rescue_incident_id,
                "rescue_target_robot_code": self.rescue_target_robot_code,
                "escort_mission_id": self.escort_mission_id,
                "escort_target_robot_code": self.escort_target_robot_code,
                "timestamp": self._now_iso(),
            },
        )

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        result = self.client.publish(
            topic,
            json.dumps(payload, ensure_ascii=False),
            qos=1,
            retain=False,
        )
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"published {topic}: {payload}")
        else:
            print(f"publish failed rc={result.rc} topic={topic}")

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: Any = None,
    ) -> None:
        if reason_code.is_failure:
            print(f"MQTT connect failed: {reason_code}")
            return
        print("MQTT connected")
        client.subscribe(f"fleet/command/{self.robot_code}", qos=1)
        client.subscribe(f"fleet/task/{self.robot_code}", qos=1)
        client.subscribe("fleet/broadcast", qos=1)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: Any = None,
    ) -> None:
        print(f"MQTT disconnected: {reason_code}")

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {"raw": message.payload.decode("utf-8", errors="replace")}
        print(f"received {message.topic}: {payload}")
        self._handle_downlink(payload)

    def _handle_downlink(self, payload: Dict[str, Any]) -> None:
        command_id = str(payload.get("command_id") or "").strip()
        command = str(payload.get("command") or "unknown").strip()
        command_payload = payload.get("payload", {})
        if not isinstance(command_payload, dict):
            command_payload = {}

        detail = "command received"
        ack_status = "accepted"
        if command in {"stop", "emergency_stop"}:
            self.mode = "idle"
            stop_result = self._execute_robot_stop()
            ack_status = "accepted" if stop_result["ok"] else "failed"
            detail = stop_result["detail"]
        elif command in {"patrol_start", "start_patrol"}:
            self.mode = "patrol"
            detail = "patrol mode accepted"
        elif command in {"follow_start", "start_follow"}:
            self.mode = "follow"
            detail = "follow mode accepted"
        elif command in {"teleop", "cmd_vel"}:
            self.mode = "teleop"
            detail = "teleop command accepted"
        elif command in {"set_mode", "mode"}:
            requested_mode = str(command_payload.get("mode") or "").strip()
            if requested_mode:
                self.mode = requested_mode
                detail = f"mode set to {requested_mode}"
        elif command == "set_formation":
            requested_mode = str(command_payload.get("mode") or "patrol").strip()
            self.mode = requested_mode or self.mode
            self.formation_id = str(command_payload.get("formation_id") or "").strip() or None
            self.formation_role = str(command_payload.get("role") or "").strip() or None
            try:
                self.formation_slot = int(command_payload.get("slot_index"))
            except (TypeError, ValueError):
                self.formation_slot = None
            detail = f"formation role set to {self.formation_role or 'unknown'}"
        elif command == "assist_robot":
            self.mode = "rescue"
            self.rescue_incident_id = str(command_payload.get("incident_id") or "").strip() or None
            self.rescue_target_robot_code = (
                str(command_payload.get("disabled_robot_code") or "").strip() or None
            )
            detail = f"rescue task accepted for {self.rescue_target_robot_code or 'unknown robot'}"
        elif command == "rescue_approach":
            self.mode = "rescue"
            self.rescue_incident_id = str(command_payload.get("incident_id") or "").strip() or None
            self.rescue_target_robot_code = (
                str(command_payload.get("disabled_robot_code") or "").strip() or None
            )
            motion_result = self._execute_limited_motion(
                command_payload,
                action_name="rescue approach",
                linear_fallback=0.08,
                linear_lower=0.0,
                linear_upper=0.12,
                angular_fallback=0.0,
                angular_lower=-0.4,
                angular_upper=0.4,
                duration_fallback=0.8,
                duration_lower=0.1,
                duration_upper=2.0,
            )
            ack_status = "accepted" if motion_result["ok"] else "failed"
            detail = motion_result["detail"]
        elif command == "rescue_search":
            self.mode = "rescue"
            self.rescue_incident_id = str(command_payload.get("incident_id") or "").strip() or None
            self.rescue_target_robot_code = (
                str(command_payload.get("disabled_robot_code") or "").strip() or None
            )
            motion_result = self._execute_limited_motion(
                command_payload,
                action_name="rescue search",
                linear_fallback=0.0,
                linear_lower=0.0,
                linear_upper=0.0,
                angular_fallback=0.25,
                angular_lower=0.1,
                angular_upper=0.4,
                duration_fallback=1.5,
                duration_lower=0.5,
                duration_upper=3.0,
            )
            ack_status = "accepted" if motion_result["ok"] else "failed"
            detail = motion_result["detail"]
        elif command == "corridor_crawl":
            self.mode = "busy"
            motion_result = self._execute_limited_motion(
                command_payload,
                action_name="corridor crawl",
                linear_fallback=0.06,
                linear_lower=0.0,
                linear_upper=0.12,
                angular_fallback=0.0,
                angular_lower=0.0,
                angular_upper=0.0,
                duration_fallback=1.0,
                duration_lower=0.2,
                duration_upper=3.0,
            )
            ack_status = "accepted" if motion_result["ok"] else "failed"
            detail = motion_result["detail"]
        elif command == "corridor_yield":
            self.mode = "busy"
            motion_result = self._execute_limited_motion(
                command_payload,
                action_name="corridor yield",
                linear_fallback=-0.05,
                linear_lower=-0.08,
                linear_upper=0.0,
                angular_fallback=0.0,
                angular_lower=0.0,
                angular_upper=0.0,
                duration_fallback=0.8,
                duration_lower=0.2,
                duration_upper=2.0,
            )
            ack_status = "accepted" if motion_result["ok"] else "failed"
            detail = motion_result["detail"]
        elif command == "hazard_avoid":
            self.mode = "busy"
            motion_result = self._execute_limited_motion(
                command_payload,
                action_name="hazard avoidance",
                linear_fallback=0.04,
                linear_lower=0.0,
                linear_upper=0.1,
                angular_fallback=0.22,
                angular_lower=-0.4,
                angular_upper=0.4,
                duration_fallback=1.0,
                duration_lower=0.2,
                duration_upper=3.0,
            )
            ack_status = "accepted" if motion_result["ok"] else "failed"
            detail = motion_result["detail"]
        elif command == "escort_return":
            self.mode = "follow"
            self.escort_mission_id = str(command_payload.get("mission_id") or "").strip() or None
            self.escort_target_robot_code = (
                str(command_payload.get("target_robot_code") or "").strip() or None
            )
            motion_result = self._execute_limited_motion(
                command_payload,
                action_name="escort return",
                linear_fallback=0.05,
                linear_lower=0.0,
                linear_upper=0.1,
                angular_fallback=0.0,
                angular_lower=-0.3,
                angular_upper=0.3,
                duration_fallback=1.0,
                duration_lower=0.2,
                duration_upper=3.0,
            )
            ack_status = "accepted" if motion_result["ok"] else "failed"
            detail = motion_result["detail"]
        elif command == "plate_verify_scan":
            self.mode = "busy"
            motion_result = self._execute_limited_motion(
                command_payload,
                action_name="plate verification scan",
                linear_fallback=0.0,
                linear_lower=0.0,
                linear_upper=0.0,
                angular_fallback=0.22,
                angular_lower=0.1,
                angular_upper=0.4,
                duration_fallback=1.5,
                duration_lower=0.5,
                duration_upper=3.0,
            )
            ack_status = "accepted" if motion_result["ok"] else "failed"
            detail = motion_result["detail"]

        self._publish(
            robot_ack_topic(self.robot_code),
            {
                "robot_code": self.robot_code,
                "command_id": command_id,
                "command": command,
                "status": ack_status,
                "detail": detail,
                "rescue_incident_id": self.rescue_incident_id,
                "rescue_target_robot_code": self.rescue_target_robot_code,
                "escort_mission_id": self.escort_mission_id,
                "escort_target_robot_code": self.escort_target_robot_code,
                "dry_run": self.dry_run,
                "timestamp": self._now_iso(),
            },
        )
        self.publish_status()

    def _execute_limited_motion(
        self,
        payload: Dict[str, Any],
        action_name: str,
        linear_fallback: float,
        linear_lower: float,
        linear_upper: float,
        angular_fallback: float,
        angular_lower: float,
        angular_upper: float,
        duration_fallback: float,
        duration_lower: float,
        duration_upper: float,
    ) -> Dict[str, Any]:
        motion = payload.get("motion", {})
        if not isinstance(motion, dict):
            motion = {}
        command = {
            "linear_x": self._float_in_range(motion.get("linear_x"), linear_fallback, linear_lower, linear_upper),
            "linear_y": 0.0,
            "angular_z": self._float_in_range(motion.get("angular_z"), angular_fallback, angular_lower, angular_upper),
            "duration": self._float_in_range(motion.get("duration"), duration_fallback, duration_lower, duration_upper),
            "rate_hz": self._float_in_range(motion.get("rate_hz"), 10.0, 1.0, 15.0),
            "wait_for_subscriber_timeout": 1.0,
        }
        schedule = payload.get("schedule", {})
        if not isinstance(schedule, dict):
            schedule = {}
        start_delay_sec = self._float_in_range(
            schedule.get("start_delay_sec"),
            0.0,
            0.0,
            10.0,
        )
        if self.dry_run:
            return {
                "ok": True,
                "detail": f"dry-run {action_name} accepted after {start_delay_sec}s delay: {command}",
            }
        if start_delay_sec > 0 and self.stop_event.wait(start_delay_sec):
            return {"ok": False, "detail": f"{action_name} cancelled before scheduled start"}
        url = f"{settings.ros_bridge_http_url.rstrip('/')}/api/teleop/cmd-vel"
        try:
            with httpx.Client(timeout=command["duration"] + 3.0) as client:
                response = client.post(url, json=command)
        except httpx.RequestError as exc:
            return {"ok": False, "detail": f"{action_name} failed: ROS bridge unreachable at {url}: {exc}"}
        if not response.is_success:
            return {
                "ok": False,
                "detail": f"{action_name} failed: ROS bridge returned HTTP {response.status_code}: {response.text}",
            }
        return {"ok": True, "detail": f"{action_name} motion accepted: {command}"}

    def _execute_robot_stop(self) -> Dict[str, Any]:
        if self.dry_run:
            return {"ok": True, "detail": "dry-run stop accepted"}
        url = f"{settings.ros_bridge_http_url.rstrip('/')}/api/teleop/stop"
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.post(url)
        except httpx.RequestError as exc:
            return {"ok": False, "detail": f"stop failed: ROS bridge unreachable at {url}: {exc}"}
        if not response.is_success:
            return {
                "ok": False,
                "detail": f"stop failed: ROS bridge returned HTTP {response.status_code}: {response.text}",
            }
        return {"ok": True, "detail": "stop command sent to ROS bridge"}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _load_deployed_commit() -> str | None:
        for parent in Path(__file__).resolve().parents:
            marker = parent / "DEPLOYED_COMMIT"
            if marker.exists():
                return marker.read_text(encoding="utf-8").strip() or None
        return None

    @staticmethod
    def _local_ip() -> str | None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return None
        finally:
            sock.close()

    @staticmethod
    def _float_in_range(value: Any, fallback: float, lower: float, upper: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = fallback
        return max(lower, min(upper, parsed))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Robot-side MQTT fleet agent")
    parser.add_argument("--robot-code", default=settings.robot_code)
    parser.add_argument(
        "--interval-sec",
        type=int,
        default=settings.robot_agent_status_interval_sec,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without reading real robot state; useful for desktop multi-robot simulation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    agent = RobotAgent(
        robot_code=args.robot_code,
        interval_sec=args.interval_sec,
        dry_run=args.dry_run,
    )

    def stop(*_: object) -> None:
        agent.stop_event.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    agent.run()


if __name__ == "__main__":
    main()
