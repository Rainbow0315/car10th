from __future__ import annotations

import os
import signal
import socketserver
import threading
from dataclasses import dataclass
from typing import Optional

from apps.ros_bridge.publishers.cmd_vel import CmdVelPublisher, RosRuntimeUnavailableError
from apps.tcp_car_bridge.audio_player import AudioPlayer
from apps.tcp_car_bridge.light_show import LightShow
from apps.tcp_car_bridge.serial_hardware import (
    HeadlightEffectController,
    SerialCarHardware,
)


def _byte(value: str) -> int:
    return int(value, 16)


@dataclass
class CarCommand:
    command: str
    data: str


class ProtocolError(ValueError):
    pass


def parse_frame(frame: str) -> CarCommand:
    frame = frame.strip()
    if not frame.startswith("$") or not frame.endswith("#"):
        raise ProtocolError(f"bad frame wrapper: {frame!r}")

    body = frame[1:-1]
    if len(body) < 8 or len(body) % 2 != 0:
        raise ProtocolError(f"bad frame length: {frame!r}")

    vehicle_type = body[0:2]
    command = body[2:4]
    declared_size = _byte(body[4:6])
    data = body[6:-2]
    checksum = _byte(body[-2:])

    if vehicle_type != "01":
        raise ProtocolError(f"unsupported vehicle type: {vehicle_type}")
    if declared_size != len(data) + 2:
        raise ProtocolError(
            f"bad declared size: declared={declared_size}, actual={len(data) + 2}"
        )

    calculated = 0
    for i in range(0, len(body) - 2, 2):
        calculated = (calculated + _byte(body[i : i + 2])) % 256
    if calculated != checksum:
        raise ProtocolError(f"bad checksum: expected={checksum:02X}, actual={calculated:02X}")

    return CarCommand(command=command, data=data)


def signed_byte(hex_value: str) -> int:
    value = _byte(hex_value)
    return value - 256 if value >= 128 else value


class TcpCarBridge:
    def __init__(self, publisher: Optional[CmdVelPublisher] = None) -> None:
        topic_name = os.getenv("ROS_CMD_VEL_TOPIC", "/cmd_vel")
        node_name = os.getenv("TCP_CAR_NODE_NAME", "tcp_car_bridge_cmd_vel")
        self.light_topic = os.getenv("ROS_RGB_LIGHT_TOPIC", "/RGBLight")
        self.publisher = publisher or CmdVelPublisher(
            topic_name=topic_name,
            node_name=node_name,
            int32_topics=(self.light_topic,),
        )
        self.linear_speed = float(os.getenv("TCP_CAR_LINEAR_SPEED", "0.18"))
        self.lateral_speed = float(os.getenv("TCP_CAR_LATERAL_SPEED", "0.18"))
        self.angular_speed = float(os.getenv("TCP_CAR_ANGULAR_SPEED", "0.9"))
        self.command_duration = float(os.getenv("TCP_CAR_COMMAND_DURATION", "0.35"))
        self.rate_hz = float(os.getenv("TCP_CAR_RATE_HZ", "10.0"))
        self.hardware: Optional[SerialCarHardware] = None
        self.headlights: Optional[HeadlightEffectController] = None
        if publisher is None:
            try:
                self.hardware = SerialCarHardware(
                    port=os.getenv("TCP_CAR_SERIAL_PORT", "/dev/myserial"),
                    baudrate=int(os.getenv("TCP_CAR_SERIAL_BAUDRATE", "115200")),
                )
                self.headlights = HeadlightEffectController(self.hardware)
                print("Physical car control enabled on /dev/myserial", flush=True)
            except Exception as exc:
                print(f"Physical car control unavailable; using ROS fallback: {exc}", flush=True)
        self.show = LightShow(set_light_scene=self._set_show_light_scene)
        self.audio = AudioPlayer()

    def handle_frame(self, frame: str) -> str:
        command = parse_frame(frame)
        if command.command == "15":
            self._handle_button(command.data)
        elif command.command == "10":
            self._handle_vector(command.data)
        elif command.command == "21":
            self._handle_wheel_speeds(command.data)
        elif command.command == "30":
            self._handle_light_effect(command.data)
        elif command.command == "31":
            if self.headlights is not None:
                self.headlights.stop()
            self.show.start()
        elif command.command == "32":
            self.show.stop()
        elif command.command == "33":
            self.audio.play()
        elif command.command in {"60", "61", "62", "63", "64"}:
            pass
        else:
            raise ProtocolError(f"unsupported command: {command.command}")
        return "OK\n"

    def _handle_button(self, data: str) -> None:
        if len(data) < 2:
            raise ProtocolError("button command missing direction")
        direction = _byte(data[0:2])
        self._stop_show_if_running()
        linear_x = 0.0
        linear_y = 0.0
        angular_z = 0.0

        if direction == 0:
            self.publisher.stop()
            return
        if direction == 1:
            linear_x = self.linear_speed
        elif direction == 2:
            linear_x = -self.linear_speed
        elif direction == 3:
            linear_y = self.lateral_speed
        elif direction == 4:
            linear_y = -self.lateral_speed
        elif direction == 5:
            angular_z = self.angular_speed
        elif direction == 6:
            angular_z = -self.angular_speed
        elif direction == 7:
            self.publisher.stop()
            return
        else:
            raise ProtocolError(f"unsupported direction: {direction}")

        self.publisher.publish_for_duration(
            linear_x=linear_x,
            linear_y=linear_y,
            angular_z=angular_z,
            duration=self.command_duration,
            rate_hz=self.rate_hz,
        )

    def _handle_vector(self, data: str) -> None:
        if len(data) < 4:
            raise ProtocolError("vector command missing x/y")
        x = signed_byte(data[0:2]) / 100.0
        y = signed_byte(data[2:4]) / 100.0
        self._stop_show_if_running()
        self.publisher.publish_for_duration(
            linear_x=y * self.linear_speed,
            linear_y=x * self.lateral_speed,
            angular_z=0.0,
            duration=self.command_duration,
            rate_hz=self.rate_hz,
        )

    def _handle_wheel_speeds(self, data: str) -> None:
        if len(data) < 8:
            raise ProtocolError("wheel command missing four speeds")
        left_front = signed_byte(data[0:2]) / 100.0
        left_rear = signed_byte(data[2:4]) / 100.0
        right_front = signed_byte(data[4:6]) / 100.0
        right_rear = signed_byte(data[6:8]) / 100.0
        self._stop_show_if_running()
        left_avg = (left_front + left_rear) / 2.0
        right_avg = (right_front + right_rear) / 2.0
        linear_x = ((left_avg + right_avg) / 2.0) * self.linear_speed
        angular_z = (right_avg - left_avg) * self.angular_speed
        self.publisher.publish_for_duration(
            linear_x=linear_x,
            linear_y=0.0,
            angular_z=angular_z,
            duration=self.command_duration,
            rate_hz=self.rate_hz,
        )

    def _handle_light_effect(self, data: str) -> None:
        if len(data) < 2:
            raise ProtocolError("light command missing effect")
        effect = _byte(data[0:2])
        if effect > 6:
            raise ProtocolError(f"unsupported light effect: {effect}")
        if self.show.is_running:
            self.show.stop(turn_off_lights=False)
        if self.headlights is not None:
            self.headlights.set_effect(effect)
        else:
            self._publish_ros_light_effect(effect)

    def _publish_ros_light_effect(self, effect: int) -> None:
        self.publisher.publish_int32(self.light_topic, effect, repeat=3)

    def _set_show_light_scene(self, scene: int) -> None:
        if self.hardware is None:
            self._publish_ros_light_effect(scene)
            return
        self.hardware.set_light_scene(scene)

    def _stop_show_if_running(self) -> None:
        if self.show.is_running:
            self.show.stop()

    def close(self) -> None:
        self.audio.stop()
        self.show.stop()
        if self.headlights is not None:
            self.headlights.stop()
        if self.hardware is not None:
            self.hardware.close()
        self.publisher.close()


bridge: Optional[TcpCarBridge] = None


class CarTcpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        assert bridge is not None
        buffer = ""
        while True:
            data = self.request.recv(1024)
            if not data:
                return
            buffer += data.decode("ascii", errors="ignore")

            while "#" in buffer:
                part, buffer = buffer.split("#", 1)
                if not part.strip():
                    continue
                frame = part + "#"
                try:
                    response = bridge.handle_frame(frame)
                except Exception as exc:
                    response = f"ERR {exc}\n"
                self.request.sendall(response.encode("ascii"))


class ThreadedTcpServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    global bridge
    host = os.getenv("TCP_CAR_HOST", "0.0.0.0")
    port = int(os.getenv("TCP_CAR_PORT", "6001"))

    try:
        bridge = TcpCarBridge()
    except RosRuntimeUnavailableError as exc:
        raise SystemExit(f"ROS runtime unavailable: {exc}") from exc

    server = ThreadedTcpServer((host, port), CarTcpHandler)

    def stop_server(*_: object) -> None:
        threading.Thread(
            target=server.shutdown,
            name="tcp-car-bridge-shutdown",
            daemon=True,
        ).start()

    signal.signal(signal.SIGINT, stop_server)
    signal.signal(signal.SIGTERM, stop_server)

    print(f"TCP car bridge listening on {host}:{port}")
    print("Protocol: Yahboom/OpenHarmony frames; light=30, show start=31, show stop=32, audio=33")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if bridge is not None:
            bridge.close()


if __name__ == "__main__":
    main()
