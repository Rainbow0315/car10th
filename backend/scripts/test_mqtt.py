"""MQTT 本地联调脚本。

用法（backend 目录）:
    python scripts/test_mqtt.py publish-status
    python scripts/test_mqtt.py publish-control
    python scripts/test_mqtt.py subscribe-status
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config.settings import settings
from common.mqtt.topics import app_control_topic, robot_status_topic


def configure_auth(client: mqtt.Client, role: str) -> None:
    if role == "app":
        username = settings.mqtt_app_username
        password = settings.mqtt_app_password
    else:
        username = settings.mqtt_username
        password = settings.mqtt_password

    if username:
        client.username_pw_set(username, password or None)


def publish_control() -> None:
    topic = app_control_topic("robot_001")
    payload = {
        "command": "stop",
        "payload": {},
    }
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    configure_auth(client, "app")
    client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, 60)
    client.loop_start()
    client.publish(topic, json.dumps(payload), qos=1)
    time.sleep(1)
    client.loop_stop()
    client.disconnect()
    print(f"published control -> {topic}: {payload}")


def publish_status() -> None:
    topic = robot_status_topic("robot_001")
    payload = {
        "robot_code": "robot_001",
        "status": "online",
        "mode": "idle",
        "battery": 88,
        "network_latency": 20,
        "pose_x": 1.2,
        "pose_y": 3.4,
        "pose_yaw": 0.0,
        "map_name": "demo_map",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    configure_auth(client, "backend")
    client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, 60)
    client.loop_start()
    client.publish(topic, json.dumps(payload), qos=1, retain=True)
    time.sleep(1)
    client.loop_stop()
    client.disconnect()
    print(f"published status -> {topic}")


def subscribe_status() -> None:
    topic = robot_status_topic("robot_001")

    def on_message(client, userdata, message):
        print(f"[{message.topic}] {message.payload.decode()}")

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    configure_auth(client, "app")
    client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, 60)
    client.subscribe(topic, qos=1)
    client.loop_start()
    print(f"listening {topic} ... Ctrl+C to exit")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "subscribe-status"
    if cmd == "publish-control":
        publish_control()
    elif cmd == "publish-status":
        publish_status()
    else:
        subscribe_status()
