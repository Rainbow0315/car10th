from __future__ import annotations

import os
import signal
import socketserver
import threading
from dataclasses import dataclass
from typing import Optional

from apps.ros_bridge.publishers.cmd_vel import CmdVelPublisher, RosRuntimeUnavailableError


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
    def __init__(self) -> None:
        topic_name = os.getenv("ROS_CMD_VEL_TOPIC", "/cmd_vel")
        node_name = os.getenv("TCP_CAR_NODE_NAME", "tcp_car_bridge_cmd_vel")
        self.publisher = CmdVelPublisher(topic_name=topic_name, node_name=node_name)
        self.linear_speed = float(os.getenv("TCP_CAR_LINEAR_SPEED", "0.18"))
        self.lateral_speed = float(os.getenv("TCP_CAR_LATERAL_SPEED", "0.18"))
        self.angular_speed = float(os.getenv("TCP_CAR_ANGULAR_SPEED", "0.9"))
        self.command_duration = float(os.getenv("TCP_CAR_COMMAND_DURATION", "0.35"))
        self.rate_hz = float(os.getenv("TCP_CAR_RATE_HZ", "10.0"))

    def handle_frame(self, frame: str) -> str:
        command = parse_frame(frame)
        if command.command == "15":
            self._handle_button(command.data)
        elif command.command == "10":
            self._handle_vector(command.data)
        elif command.command == "21":
            self._handle_wheel_speeds(command.data)
        elif command.command in {"60", "61", "62", "63", "64"}:
            pass
        else:
            raise ProtocolError(f"unsupported command: {command.command}")
        return "OK\n"

    def _handle_button(self, data: str) -> None:
        if len(data) < 2:
            raise ProtocolError("button command missing direction")
        direction = _byte(data[0:2])
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

    def close(self) -> None:
        self.publisher.close()


bridge: Optional[TcpCarBridge] = None


class CarTcpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        assert bridge is not None
        data = self.request.recv(1024)
        if not data:
            return
        text = data.decode("ascii", errors="ignore")
        frames = [part for part in text.split("#") if part.strip()]
        for part in frames:
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
    port = int(os.getenv("TCP_CAR_PORT", "6000"))

    try:
        bridge = TcpCarBridge()
    except RosRuntimeUnavailableError as exc:
        raise SystemExit(f"ROS runtime unavailable: {exc}") from exc

    server = ThreadedTcpServer((host, port), CarTcpHandler)

    def stop_server(*_: object) -> None:
        server.shutdown()

    signal.signal(signal.SIGINT, stop_server)
    signal.signal(signal.SIGTERM, stop_server)

    print(f"TCP car bridge listening on {host}:{port}")
    print("Protocol: Yahboom/OpenHarmony frames, e.g. $011504011B#")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if bridge is not None:
            bridge.close()


if __name__ == "__main__":
    main()
