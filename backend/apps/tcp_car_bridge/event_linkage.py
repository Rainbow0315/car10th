from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from sensor_msgs.msg import LaserScan
except ImportError:  # pragma: no cover - only happens outside ROS runtime
    rclpy = None
    SingleThreadedExecutor = None
    LaserScan = None

from apps.ros_bridge.publishers.cmd_vel import RosRuntimeUnavailableError


@dataclass(frozen=True)
class ObstacleWarningConfig:
    scan_topic: str = "/scan"
    distance_m: float = 0.5
    clear_distance_m: float = 0.75
    front_angle_deg: float = 35.0
    cooldown_sec: float = 5.0
    startup_grace_sec: float = 8.0
    clear_dwell_sec: float = 2.0


def nearest_front_obstacle_distance(
    ranges: Sequence[float],
    *,
    angle_min: float,
    angle_increment: float,
    range_min: float,
    range_max: float,
    front_angle_deg: float,
) -> Optional[float]:
    front_angle_rad = math.radians(max(0.0, front_angle_deg))
    nearest: Optional[float] = None

    for index, raw_distance in enumerate(ranges):
        distance = float(raw_distance)
        if not math.isfinite(distance):
            continue
        if distance < range_min or distance > range_max:
            continue

        angle = float(angle_min) + float(angle_increment) * index
        if abs(_normalize_angle(angle)) > front_angle_rad:
            continue

        if nearest is None or distance < nearest:
            nearest = distance

    return nearest


class ObstacleSoundLightMonitor:
    def __init__(
        self,
        on_warning: Callable[[float], None],
        config: ObstacleWarningConfig,
        node_name: str = "tcp_car_bridge_obstacle_events",
    ) -> None:
        if rclpy is None or LaserScan is None or SingleThreadedExecutor is None:
            raise RosRuntimeUnavailableError(
                "ROS 2 LaserScan runtime is unavailable. Please source the ROS 2 environment on the robot first."
            )

        self._on_warning = on_warning
        self._config = config
        self._lock = threading.Lock()
        self._last_warning_at = 0.0
        self._front_blocked = True
        self._clear_since: Optional[float] = None
        self._started_at = time.monotonic()
        self._closed = False
        self._owns_rclpy_context = False

        if not rclpy.ok():
            rclpy.init()
            self._owns_rclpy_context = True

        self._node = rclpy.create_node(node_name)
        self._node.create_subscription(LaserScan, config.scan_topic, self._on_scan, 10)
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(
            target=self._executor.spin,
            name="tcp-car-obstacle-events",
            daemon=True,
        )
        self._spin_thread.start()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown()
        self._node.destroy_node()
        if self._owns_rclpy_context and rclpy.ok():
            rclpy.shutdown()

    def _on_scan(self, msg: Any) -> None:
        nearest = nearest_front_obstacle_distance(
            msg.ranges,
            angle_min=float(msg.angle_min),
            angle_increment=float(msg.angle_increment),
            range_min=float(msg.range_min),
            range_max=float(msg.range_max),
            front_angle_deg=self._config.front_angle_deg,
        )
        now = time.monotonic()
        blocked = nearest is not None and nearest <= self._config.distance_m
        clear = nearest is None or nearest >= self._config.clear_distance_m
        if clear:
            with self._lock:
                if self._clear_since is None:
                    self._clear_since = now
                elif now - self._clear_since >= self._config.clear_dwell_sec:
                    self._front_blocked = False
            return
        if not blocked:
            return

        with self._lock:
            if self._closed:
                return
            if now - self._started_at < self._config.startup_grace_sec:
                self._front_blocked = blocked
                self._clear_since = None
                return
            if self._front_blocked:
                return
            self._front_blocked = True
            self._clear_since = None
            if now - self._last_warning_at < self._config.cooldown_sec:
                return
            self._last_warning_at = now

        try:
            assert nearest is not None
            self._on_warning(nearest)
        except Exception as exc:
            print(f"Obstacle warning callback failed: {exc}", flush=True)


def _normalize_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle
