from __future__ import annotations

import math
import threading
from typing import Any

try:
    import rclpy
    from geometry_msgs.msg import PoseWithCovarianceStamped
    from rclpy.executors import SingleThreadedExecutor
except ImportError:  # pragma: no cover - only happens outside ROS runtime
    rclpy = None
    PoseWithCovarianceStamped = None
    SingleThreadedExecutor = None

from apps.ros_bridge.publishers.cmd_vel import RosRuntimeUnavailableError


class InitialPosePublisher:
    def __init__(
        self,
        topic_name: str = "/initialpose",
        node_name: str = "ros_bridge_initial_pose",
    ) -> None:
        if rclpy is None or PoseWithCovarianceStamped is None or SingleThreadedExecutor is None:
            raise RosRuntimeUnavailableError(
                "ROS 2 Python runtime is unavailable. Please source the ROS 2 environment on the robot first."
            )

        self._topic_name = topic_name
        self._node_name = node_name
        self._lock = threading.Lock()
        self._closed = False
        self._owns_rclpy_context = False

        if not rclpy.ok():
            rclpy.init()
            self._owns_rclpy_context = True

        self._node = rclpy.create_node(node_name)
        self._publisher = self._node.create_publisher(PoseWithCovarianceStamped, topic_name, 10)
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

    def publish_initial_pose(self, x: float, y: float, yaw: float = 0.0, frame_id: str = "map") -> None:
        with self._lock:
            self._ensure_open()
            msg = PoseWithCovarianceStamped()
            msg.header.frame_id = frame_id
            msg.header.stamp = self._node.get_clock().now().to_msg()
            msg.pose.pose.position.x = float(x)
            msg.pose.pose.position.y = float(y)
            msg.pose.pose.position.z = 0.0
            msg.pose.pose.orientation = _quaternion_from_yaw(float(yaw))
            msg.pose.covariance[0] = 0.25
            msg.pose.covariance[7] = 0.25
            msg.pose.covariance[35] = 0.0685
            self._publisher.publish(msg)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._executor.shutdown()
            self._node.destroy_node()
            if self._owns_rclpy_context and rclpy.ok():
                rclpy.shutdown()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("initial pose publisher has already been closed")


def _quaternion_from_yaw(yaw: float) -> Any:
    q = PoseWithCovarianceStamped().pose.pose.orientation
    q.x = 0.0
    q.y = 0.0
    q.z = math.sin(yaw / 2.0)
    q.w = math.cos(yaw / 2.0)
    return q
