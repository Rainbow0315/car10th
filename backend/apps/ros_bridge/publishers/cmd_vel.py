from __future__ import annotations

import threading
import time
from typing import Optional, Sequence

try:
    import rclpy
    from geometry_msgs.msg import Twist
    from rclpy.executors import SingleThreadedExecutor
    from std_msgs.msg import Int32
except ImportError:  # pragma: no cover - only happens outside ROS runtime
    rclpy = None
    Twist = None
    SingleThreadedExecutor = None
    Int32 = None


class RosRuntimeUnavailableError(RuntimeError):
    pass


class CmdVelPublisher:
    def __init__(
        self,
        topic_name: str = "/cmd_vel",
        node_name: str = "ros_bridge_cmd_vel",
        int32_topics: Optional[Sequence[str]] = None,
    ) -> None:
        if rclpy is None or Twist is None or SingleThreadedExecutor is None:
            raise RosRuntimeUnavailableError(
                "ROS 2 Python runtime is unavailable. Please source the ROS 2 environment on the robot first."
            )

        self._topic_name = topic_name
        self._lock = threading.Lock()
        self._closed = False
        self._owns_rclpy_context = False
        self._node_name = node_name
        self._active_stop_event: Optional[threading.Event] = None
        self._active_thread: Optional[threading.Thread] = None
        self._int32_publishers = {}

        if not rclpy.ok():
            rclpy.init()
            self._owns_rclpy_context = True

        self._node = rclpy.create_node(node_name)
        self._publisher = self._node.create_publisher(Twist, topic_name, 10)
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
    def node_name(self) -> str:
        return self._node_name

    def subscription_count(self) -> int:
        with self._lock:
            self._ensure_open()
            return self._publisher.get_subscription_count()

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

    def _build_twist(self, linear_x: float, linear_y: float, angular_z: float) -> Twist:
        msg = Twist()
        msg.linear.x = float(linear_x)
        msg.linear.y = float(linear_y)
        msg.angular.z = float(angular_z)
        return msg

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
