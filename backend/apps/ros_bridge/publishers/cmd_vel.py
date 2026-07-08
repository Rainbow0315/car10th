from __future__ import annotations

import threading
import time

try:
    import rclpy
    from geometry_msgs.msg import Twist
    from rclpy.executors import SingleThreadedExecutor
except ImportError:  # pragma: no cover - only happens outside ROS runtime
    rclpy = None
    Twist = None
    SingleThreadedExecutor = None


class RosRuntimeUnavailableError(RuntimeError):
    pass


class CmdVelPublisher:
    def __init__(self, topic_name: str = "/cmd_vel", node_name: str = "ros_bridge_cmd_vel") -> None:
        if rclpy is None or Twist is None or SingleThreadedExecutor is None:
            raise RosRuntimeUnavailableError(
                "ROS 2 Python runtime is unavailable. Please source the ROS 2 environment on the robot first."
            )

        self._topic_name = topic_name
        self._lock = threading.Lock()
        self._closed = False
        self._owns_rclpy_context = False

        if not rclpy.ok():
            rclpy.init()
            self._owns_rclpy_context = True

        self._node = rclpy.create_node(node_name)
        self._publisher = self._node.create_publisher(Twist, topic_name, 10)
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._spin_thread.start()

    @property
    def topic_name(self) -> str:
        return self._topic_name

    def publish_once(self, linear_x: float, linear_y: float, angular_z: float, repeat: int = 5) -> None:
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
        worker = threading.Thread(
            target=self._run_timed_publish,
            args=(linear_x, linear_y, angular_z, duration, rate_hz),
            daemon=True,
        )
        worker.start()

    def stop(self) -> None:
        self.publish_once(0.0, 0.0, 0.0, repeat=3)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._executor.shutdown()
            self._node.destroy_node()
            if self._owns_rclpy_context and rclpy.ok():
                rclpy.shutdown()

    def _run_timed_publish(
        self,
        linear_x: float,
        linear_y: float,
        angular_z: float,
        duration: float,
        rate_hz: float,
    ) -> None:
        interval = 1.0 / max(rate_hz, 1.0)
        end_time = time.monotonic() + duration
        msg = self._build_twist(linear_x, linear_y, angular_z)

        while time.monotonic() < end_time:
            with self._lock:
                if self._closed:
                    return
                self._publisher.publish(msg)
            time.sleep(interval)

        self.stop()

    def _build_twist(self, linear_x: float, linear_y: float, angular_z: float) -> Twist:
        msg = Twist()
        msg.linear.x = float(linear_x)
        msg.linear.y = float(linear_y)
        msg.angular.z = float(angular_z)
        return msg

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("cmd_vel publisher has already been closed")
