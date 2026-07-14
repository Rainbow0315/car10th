from __future__ import annotations

import os
import signal
import subprocess
import socketserver
import threading
from dataclasses import dataclass
from typing import Optional

from apps.ros_bridge.publishers.cmd_vel import CmdVelPublisher, RosRuntimeUnavailableError
from apps.tcp_car_bridge.audio_player import AudioPlayer
from apps.tcp_car_bridge.event_linkage import (
    ObstacleSoundLightMonitor,
    ObstacleWarningConfig,
)
from apps.tcp_car_bridge.light_show import LightShow
from apps.tcp_car_bridge.serial_hardware import (
    HeadlightEffectController,
    LIGHT_LEFT,
    LIGHT_OFF,
    LIGHT_ON,
    LIGHT_RIGHT,
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


class ExternalCommandError(RuntimeError):
    pass


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


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
        self.track_start_command = os.getenv(
            "TCP_CAR_TRACK_START_COMMAND",
            "bash -lc 'source /opt/ros/foxy/setup.bash; "
            "source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash; "
            "source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash; "
            "exec ros2 run yahboomcar_laser laser_Tracker_a1_X3 "
            "> /tmp/laser_tracker_app.log 2>&1'",
        )
        self.track_stop_command = os.getenv(
            "TCP_CAR_TRACK_STOP_COMMAND",
            "bash -lc 'pkill -f \"[l]aser_Tracker_a1_X3\" || true'",
        )
        self.track_command_timeout = float(os.getenv("TCP_CAR_TRACK_COMMAND_TIMEOUT", "8.0"))
        self._tracking_process: Optional[subprocess.Popen] = None
        self.hardware: Optional[SerialCarHardware] = None
        self.headlights: Optional[HeadlightEffectController] = None
        self._stop_thread: Optional[threading.Thread] = None
        self._stop_lock = threading.Lock()
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
        self._obstacle_monitor: Optional[ObstacleSoundLightMonitor] = None
        if publisher is None and _env_bool("TCP_CAR_OBSTACLE_MONITOR_ENABLED", False):
            self._start_obstacle_monitor()

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
            self._handle_audio(command.data)
        elif command.command in {"60", "61", "62"}:
            pass
        elif command.command == "63":
            self._handle_tracking_start()
        elif command.command == "64":
            self._handle_tracking_stop()
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
            self._set_motion_light_scene(LIGHT_OFF)
            self._request_motion_stop()
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
            self._set_motion_light_scene(LIGHT_OFF)
            self._request_motion_stop()
            return
        else:
            raise ProtocolError(f"unsupported direction: {direction}")

        self._set_light_for_direction(direction)
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

    def _handle_audio(self, data: str) -> None:
        track_index = 0
        volume_percent = 80
        if len(data) >= 2:
            track_index = _byte(data[0:2])
        if len(data) >= 4:
            volume_percent = _byte(data[2:4])
        if volume_percent > 100:
            raise ProtocolError(f"unsupported audio volume: {volume_percent}")
        self.audio.play(track_index=track_index, volume_percent=volume_percent)

    def _request_motion_stop(self) -> None:
        with self._stop_lock:
            if self._stop_thread is not None and self._stop_thread.is_alive():
                return
            thread = threading.Thread(
                target=self._stop_motion_worker,
                name="tcp-car-bridge-stop",
                daemon=True,
            )
            self._stop_thread = thread
            thread.start()

    def _stop_motion_worker(self) -> None:
        try:
            self.publisher.stop()
        except Exception as exc:
            print(f"Failed to publish stop command: {exc}", flush=True)
        finally:
            with self._stop_lock:
                if self._stop_thread is threading.current_thread():
                    self._stop_thread = None

    def _publish_ros_light_effect(self, effect: int) -> None:
        self.publisher.publish_int32(self.light_topic, effect, repeat=3)

    def _start_obstacle_monitor(self) -> None:
        config = ObstacleWarningConfig(
            scan_topic=os.getenv("TCP_CAR_OBSTACLE_SCAN_TOPIC", "/scan"),
            distance_m=float(os.getenv("TCP_CAR_OBSTACLE_DISTANCE_M", "0.5")),
            clear_distance_m=float(os.getenv("TCP_CAR_OBSTACLE_CLEAR_DISTANCE_M", "0.75")),
            front_angle_deg=float(os.getenv("TCP_CAR_OBSTACLE_FRONT_DEG", "35")),
            cooldown_sec=float(os.getenv("TCP_CAR_OBSTACLE_COOLDOWN_SEC", "5")),
            startup_grace_sec=float(os.getenv("TCP_CAR_OBSTACLE_STARTUP_GRACE_SEC", "8")),
            clear_dwell_sec=float(os.getenv("TCP_CAR_OBSTACLE_CLEAR_DWELL_SEC", "2")),
        )
        try:
            self._obstacle_monitor = ObstacleSoundLightMonitor(
                on_warning=self._handle_front_obstacle_warning,
                config=config,
            )
            print(
                "Obstacle sound/light monitor enabled: "
                f"topic={config.scan_topic}, distance={config.distance_m:.2f}m, "
                f"clear_distance={config.clear_distance_m:.2f}m, "
                f"front={config.front_angle_deg:.0f}deg, cooldown={config.cooldown_sec:.1f}s, "
                f"startup_grace={config.startup_grace_sec:.1f}s, "
                f"clear_dwell={config.clear_dwell_sec:.1f}s",
                flush=True,
            )
        except RosRuntimeUnavailableError as exc:
            print(f"Obstacle sound/light monitor unavailable: {exc}", flush=True)
        except Exception as exc:
            print(f"Obstacle sound/light monitor failed to start: {exc}", flush=True)

    def _handle_front_obstacle_warning(self, distance_m: float) -> None:
        print(f"Front obstacle warning triggered at {distance_m:.2f}m", flush=True)
        self._stop_show_if_running()
        if self.headlights is not None:
            self.headlights.stop(turn_off=False)
        self._set_show_light_scene(LIGHT_ON)
        self.audio.play(track_index=0, volume_percent=100)

    def _set_light_for_direction(self, direction: int) -> None:
        if direction in {3, 5}:
            self._set_motion_light_scene(LIGHT_LEFT)
        elif direction in {4, 6}:
            self._set_motion_light_scene(LIGHT_RIGHT)
        elif direction in {1, 2}:
            self._set_motion_light_scene(LIGHT_ON)

    def _set_motion_light_scene(self, scene: int) -> None:
        self._stop_show_if_running()
        if self.headlights is not None:
            self.headlights.stop(turn_off=False)
        self._set_show_light_scene(scene)

    def _handle_tracking_start(self) -> None:
        self._stop_show_if_running()
        self._run_external_command("tracking pre-stop", self.track_stop_command)
        self._start_external_command("tracking start", self.track_start_command)

    def _handle_tracking_stop(self) -> None:
        self._run_external_command("tracking stop", self.track_stop_command)
        self._tracking_process = None
        self.publisher.stop()

    def _start_external_command(self, label: str, command: str) -> None:
        if not command.strip():
            raise ExternalCommandError(f"{label} command is empty")
        try:
            self._tracking_process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise ExternalCommandError(f"{label} command failed to start: {exc}") from exc

    def _run_external_command(self, label: str, command: str) -> None:
        if not command.strip():
            raise ExternalCommandError(f"{label} command is empty")
        try:
            result = subprocess.run(
                command,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.track_command_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExternalCommandError(
                f"{label} command timed out after {self.track_command_timeout:.1f}s"
            ) from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            if detail:
                raise ExternalCommandError(
                    f"{label} command failed with exit {result.returncode}: {detail}"
                )
            raise ExternalCommandError(f"{label} command failed with exit {result.returncode}")

    def _set_show_light_scene(self, scene: int) -> None:
        if self.hardware is None:
            self._publish_ros_light_effect(scene)
            return
        self.hardware.set_light_scene(scene)

    def _stop_show_if_running(self) -> None:
        if self.show.is_running:
            self.show.stop()

    def close(self) -> None:
        if self._obstacle_monitor is not None:
            self._obstacle_monitor.close()
        self.audio.stop()
        self.show.stop()
        if self.headlights is not None:
            self.headlights.stop()
        stop_thread = self._stop_thread
        if stop_thread is not None and stop_thread is not threading.current_thread():
            stop_thread.join(timeout=1.0)
        if self.hardware is not None:
            self.hardware.close()
        self.publisher.close()


bridge: Optional[TcpCarBridge] = None


class CarTcpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        assert bridge is not None
        buffer = ""
        while True:
            try:
                data = self.request.recv(1024)
            except ConnectionResetError:
                return
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
                try:
                    self.request.sendall(response.encode("ascii"))
                except (BrokenPipeError, ConnectionResetError):
                    return


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
    print(
        "Protocol: Yahboom/OpenHarmony frames; light=30, show start=31, "
        "show stop=32, audio=33(track,volume)"
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if bridge is not None:
            bridge.close()


if __name__ == "__main__":
    main()
