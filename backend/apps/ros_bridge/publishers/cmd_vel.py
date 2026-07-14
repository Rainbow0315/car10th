from __future__ import annotations

import math
import threading
import time
from typing import Any, Dict, Optional, Sequence

try:
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy
    from sensor_msgs.msg import Imu
    from std_msgs.msg import Int32
except ImportError:  # pragma: no cover - only happens outside ROS runtime
    rclpy = None
    Twist = None
    Odometry = None
    SingleThreadedExecutor = None
    QoSProfile = None
    QoSReliabilityPolicy = None
    Imu = None
    Int32 = None


class RosRuntimeUnavailableError(RuntimeError):
    pass


class CmdVelPublisher:
    def __init__(
        self,
        topic_name: str = "/cmd_vel",
        odom_topic_name: str = "/odom",
        imu_topic_name: str = "/imu/data",
        node_name: str = "ros_bridge_cmd_vel",
        int32_topics: Optional[Sequence[str]] = None,
    ) -> None:
        if (
            rclpy is None
            or Twist is None
            or Odometry is None
            or Imu is None
            or SingleThreadedExecutor is None
            or QoSProfile is None
            or QoSReliabilityPolicy is None
        ):
            raise RosRuntimeUnavailableError(
                "ROS 2 Python runtime is unavailable. Please source the ROS 2 environment on the robot first."
            )

        self._topic_name = topic_name
        self._odom_topic_name = odom_topic_name
        self._imu_topic_name = imu_topic_name
        self._lock = threading.Lock()
        self._closed = False
        self._owns_rclpy_context = False
        self._node_name = node_name
        self._active_stop_event: Optional[threading.Event] = None
        self._active_thread: Optional[threading.Thread] = None
        self._int32_publishers = {}
        self._latest_yaw: Optional[float] = None
        self._latest_yaw_monotonic: Optional[float] = None
        self._latest_yaw_source: Optional[str] = None
        self._latest_yaw_by_source: Dict[str, tuple[float, float]] = {}

        if not rclpy.ok():
            rclpy.init()
            self._owns_rclpy_context = True

        self._node = rclpy.create_node(node_name)
        self._publisher = self._node.create_publisher(Twist, topic_name, 10)
        sensor_qos = QoSProfile(depth=10)
        sensor_qos.reliability = QoSReliabilityPolicy.BEST_EFFORT
        self._node.create_subscription(Odometry, odom_topic_name, self._on_odom, sensor_qos)
        self._node.create_subscription(Imu, imu_topic_name, self._on_imu, sensor_qos)
        for int32_topic in int32_topics or ():
            if Int32 is None:
                raise RosRuntimeUnavailableError("ROS 2 std_msgs runtime is unavailable.")
            self._int32_publishers[int32_topic] = self._node.create_publisher(
                Int32,
                int32_topic,
                10,
            )
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._spin_thread.start()

    @property
    def topic_name(self) -> str:
        return self._topic_name

    @property
    def odom_topic_name(self) -> str:
        return self._odom_topic_name

    @property
    def imu_topic_name(self) -> str:
        return self._imu_topic_name

    @property
    def node_name(self) -> str:
        return self._node_name

    @property
    def yaw_source(self) -> Optional[str]:
        with self._lock:
            sample = self._select_yaw_locked(max_age_sec=2.0)
            return sample["source"] if sample is not None else None

    def subscription_count(self) -> int:
        with self._lock:
            self._ensure_open()
            return self._publisher.get_subscription_count()

    def odom_ready(self, max_age_sec: float = 2.0) -> bool:
        with self._lock:
            return self._select_yaw_locked(max_age_sec=max_age_sec) is not None

    def wait_for_subscribers(self, timeout: float = 2.0, min_count: int = 1, poll_interval: float = 0.05) -> int:
        deadline = time.monotonic() + max(0.0, timeout)
        target_count = max(0, min_count)

        while True:
            count = self.subscription_count()
            if count >= target_count:
                return count
            if time.monotonic() >= deadline:
                return count
            time.sleep(max(0.01, poll_interval))

    def wait_for_yaw(
        self,
        timeout: float = 2.0,
        max_age_sec: float = 1.0,
        poll_interval: float = 0.02,
        source: Optional[str] = None,
    ) -> Optional[float]:
        sample = self.wait_for_yaw_sample(
            timeout=timeout,
            max_age_sec=max_age_sec,
            poll_interval=poll_interval,
            source=source,
        )
        return sample["yaw"] if sample is not None else None

    def wait_for_yaw_sample(
        self,
        timeout: float = 2.0,
        max_age_sec: float = 1.0,
        poll_interval: float = 0.02,
        source: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            sample = self.latest_yaw_sample(max_age_sec=max_age_sec, source=source)
            if sample is not None:
                return sample
            if time.monotonic() >= deadline:
                return None
            time.sleep(max(0.01, poll_interval))

    def latest_yaw(self, max_age_sec: float = 1.0, source: Optional[str] = None) -> Optional[float]:
        sample = self.latest_yaw_sample(max_age_sec=max_age_sec, source=source)
        return sample["yaw"] if sample is not None else None

    def latest_yaw_sample(self, max_age_sec: float = 1.0, source: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._select_yaw_locked(max_age_sec=max_age_sec, source=source)

    def publish_once(self, linear_x: float, linear_y: float, angular_z: float, repeat: int = 5) -> None:
        self._cancel_active_motion(wait=True)
        self._publish_repeated(linear_x, linear_y, angular_z, repeat=repeat)

    def _publish_repeated(self, linear_x: float, linear_y: float, angular_z: float, repeat: int = 5) -> None:
        with self._lock:
            self._ensure_open()
            msg = self._build_twist(linear_x, linear_y, angular_z)
            for _ in range(max(1, repeat)):
                self._publisher.publish(msg)
                time.sleep(0.03)

    def publish_for_duration(
        self,
        linear_x: float,
        linear_y: float,
        angular_z: float,
        duration: float,
        rate_hz: float = 10.0,
    ) -> None:
        self._cancel_active_motion(wait=False)
        stop_event = threading.Event()
        worker = threading.Thread(
            target=self._run_timed_publish,
            args=(linear_x, linear_y, angular_z, duration, rate_hz, stop_event),
            daemon=True,
        )
        with self._lock:
            self._ensure_open()
            self._active_stop_event = stop_event
            self._active_thread = worker
        worker.start()

    def stop(self) -> None:
        self._cancel_active_motion(wait=False)
        self._publish_repeated(0.0, 0.0, 0.0, repeat=3)

    def rotate_angle(
        self,
        *,
        angle_rad: float,
        angular_z: float,
        tolerance_rad: float = 0.08,
        rate_hz: float = 20.0,
        timeout_sec: float = 20.0,
        wait_for_subscriber_timeout: float = 2.0,
        wait_for_odom_timeout: float = 2.0,
    ) -> Dict[str, Any]:
        self._cancel_active_motion(wait=True)
        subscriber_count = self.wait_for_subscribers(timeout=wait_for_subscriber_timeout)
        if subscriber_count < 1:
            return {
                "ok": False,
                "reason": "no_cmd_vel_subscriber",
                "subscriber_count": subscriber_count,
            }

        target = abs(float(angle_rad))
        if target <= 0.0:
            self.stop()
            yaw = self.latest_yaw(max_age_sec=10.0)
            return {
                "ok": True,
                "reason": "zero_angle",
                "subscriber_count": subscriber_count,
                "start_yaw": yaw,
                "end_yaw": yaw,
                "actual_angle_rad": 0.0,
                "elapsed_sec": 0.0,
                "average_angular_speed_rad_s": 0.0,
            }

        direction = 1.0 if angle_rad > 0.0 else -1.0
        max_speed = min(1.5, max(0.05, abs(float(angular_z)))) * direction
        tolerance = min(0.3, max(0.01, abs(float(tolerance_rad))))
        rate = min(50.0, max(5.0, float(rate_hz)))
        interval = 1.0 / rate
        timeout = min(60.0, max(1.0, float(timeout_sec)))

        start_sample = self.wait_for_yaw_sample(timeout=wait_for_odom_timeout)
        if start_sample is None:
            return {
                "ok": False,
                "reason": "odom_yaw_unavailable",
                "subscriber_count": subscriber_count,
            }
        start_yaw = float(start_sample["yaw"])
        yaw_source = str(start_sample["source"])

        stop_event = threading.Event()
        current_thread = threading.current_thread()
        with self._lock:
            self._ensure_open()
            self._active_stop_event = stop_event
            self._active_thread = current_thread

        started = time.monotonic()
        previous_yaw = start_yaw
        accumulated = 0.0
        iterations = 0
        timed_out = False
        cancelled = False

        try:
            while abs(accumulated) < max(0.0, target - tolerance):
                if stop_event.is_set():
                    cancelled = True
                    break
                elapsed = time.monotonic() - started
                if elapsed >= timeout:
                    timed_out = True
                    break

                yaw = self.wait_for_yaw(
                    timeout=min(interval, 0.05),
                    max_age_sec=0.5,
                    source=yaw_source,
                )
                if yaw is not None:
                    delta = _normalize_angle(yaw - previous_yaw)
                    accumulated += delta
                    previous_yaw = yaw

                remaining = max(0.0, target - abs(accumulated))
                slow_down_angle = max(0.8, min(2.5, target * 0.35))
                min_scale = 0.12 if remaining < 0.35 else 0.18
                speed_scale = min(1.0, max(min_scale, remaining / slow_down_angle))
                self._publish_twist(0.0, 0.0, max_speed * speed_scale)
                iterations += 1
                stop_event.wait(interval)
        finally:
            self._publish_repeated(0.0, 0.0, 0.0, repeat=5)
            self._clear_active_motion(stop_event)

        elapsed = max(0.0, time.monotonic() - started)
        end_yaw = self.latest_yaw(max_age_sec=2.0, source=yaw_source)
        average_speed = abs(accumulated) / elapsed if elapsed > 0.0 else 0.0
        ok = not timed_out and not cancelled and abs(abs(accumulated) - target) <= max(tolerance * 2.0, 0.12)
        return {
            "ok": ok,
            "reason": "completed" if ok else ("cancelled" if cancelled else "timeout" if timed_out else "angle_error"),
            "subscriber_count": subscriber_count,
            "start_yaw": start_yaw,
            "end_yaw": end_yaw,
            "yaw_source": yaw_source,
            "target_angle_rad": direction * target,
            "actual_angle_rad": accumulated,
            "abs_actual_angle_rad": abs(accumulated),
            "error_rad": direction * target - accumulated,
            "elapsed_sec": round(elapsed, 3),
            "average_angular_speed_rad_s": round(average_speed, 4),
            "iterations": iterations,
            "tolerance_rad": tolerance,
        }

    def publish_int32(
        self,
        topic_name: str,
        value: int,
        repeat: int = 3,
        wait_for_subscriber_timeout: float = 1.0,
    ) -> None:
        if Int32 is None:
            raise RosRuntimeUnavailableError("ROS 2 std_msgs runtime is unavailable.")

        with self._lock:
            self._ensure_open()
            publisher = self._int32_publishers.get(topic_name)
            if publisher is None:
                publisher = self._node.create_publisher(Int32, topic_name, 10)
                self._int32_publishers[topic_name] = publisher
            deadline = time.monotonic() + max(0.0, wait_for_subscriber_timeout)
            while (
                publisher.get_subscription_count() < 1
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            message = Int32()
            message.data = int(value)
            for _ in range(max(1, repeat)):
                publisher.publish(message)
                time.sleep(0.03)

    def close(self) -> None:
        active_thread = self._cancel_active_motion(wait=True)
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._executor.shutdown()
            self._node.destroy_node()
            if self._owns_rclpy_context and rclpy.ok():
                rclpy.shutdown()
        if active_thread is not None and active_thread is not threading.current_thread():
            active_thread.join(timeout=1.0)

    def _run_timed_publish(
        self,
        linear_x: float,
        linear_y: float,
        angular_z: float,
        duration: float,
        rate_hz: float,
        stop_event: threading.Event,
    ) -> None:
        interval = 1.0 / max(rate_hz, 1.0)
        end_time = time.monotonic() + duration
        msg = self._build_twist(linear_x, linear_y, angular_z)

        while time.monotonic() < end_time and not stop_event.is_set():
            with self._lock:
                if self._closed:
                    return
                self._publisher.publish(msg)
            stop_event.wait(interval)

        if not stop_event.is_set():
            self._publish_repeated(0.0, 0.0, 0.0, repeat=3)
        self._clear_active_motion(stop_event)

    def _publish_twist(self, linear_x: float, linear_y: float, angular_z: float) -> None:
        with self._lock:
            self._ensure_open()
            self._publisher.publish(self._build_twist(linear_x, linear_y, angular_z))

    def _build_twist(self, linear_x: float, linear_y: float, angular_z: float) -> Twist:
        msg = Twist()
        msg.linear.x = float(linear_x)
        msg.linear.y = float(linear_y)
        msg.angular.z = float(angular_z)
        return msg

    def _on_odom(self, msg: Any) -> None:
        yaw = _yaw_from_quaternion(msg.pose.pose.orientation)
        self._set_latest_yaw(yaw, "odom")

    def _on_imu(self, msg: Any) -> None:
        yaw = _yaw_from_quaternion(msg.orientation)
        self._set_latest_yaw(yaw, "imu")

    def _set_latest_yaw(self, yaw: float, source: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._latest_yaw = yaw
            self._latest_yaw_monotonic = now
            self._latest_yaw_source = source
            self._latest_yaw_by_source[source] = (yaw, now)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("cmd_vel publisher has already been closed")

    def _cancel_active_motion(self, *, wait: bool = True) -> Optional[threading.Thread]:
        with self._lock:
            stop_event = self._active_stop_event
            active_thread = self._active_thread
            self._active_stop_event = None
            self._active_thread = None
            if stop_event is not None:
                stop_event.set()

        if wait and active_thread is not None and active_thread is not threading.current_thread():
            active_thread.join(timeout=1.0)
        return active_thread

    def _clear_active_motion(self, stop_event: threading.Event) -> None:
        with self._lock:
            if self._active_stop_event is stop_event:
                self._active_stop_event = None
                self._active_thread = None

    def _select_yaw_locked(self, max_age_sec: float, source: Optional[str] = None) -> Optional[Dict[str, Any]]:
        now = time.monotonic()
        max_age = max(0.0, max_age_sec)
        if source:
            sample = self._latest_yaw_by_source.get(source)
            if sample is None:
                return None
            yaw, updated_at = sample
            if now - updated_at > max_age:
                return None
            return {"yaw": yaw, "source": source, "age_sec": now - updated_at}

        for candidate in ("odom", "imu"):
            sample = self._latest_yaw_by_source.get(candidate)
            if sample is None:
                continue
            yaw, updated_at = sample
            if now - updated_at <= max_age:
                return {"yaw": yaw, "source": candidate, "age_sec": now - updated_at}
        return None


def _normalize_angle(value: float) -> float:
    return math.atan2(math.sin(value), math.cos(value))


def _yaw_from_quaternion(q: Any) -> float:
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)
