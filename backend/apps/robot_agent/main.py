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
        if command in {"stop", "emergency_stop"}:
            self.mode = "idle"
            detail = "stop accepted"
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

        self._publish(
            robot_ack_topic(self.robot_code),
            {
                "robot_code": self.robot_code,
                "command_id": command_id,
                "command": command,
                "status": "accepted",
                "detail": detail,
                "rescue_incident_id": self.rescue_incident_id,
                "rescue_target_robot_code": self.rescue_target_robot_code,
                "dry_run": self.dry_run,
                "timestamp": self._now_iso(),
            },
        )
        self.publish_status()

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
