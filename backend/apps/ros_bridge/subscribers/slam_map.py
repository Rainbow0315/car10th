from __future__ import annotations

import math
import threading
from typing import Any, Dict, Optional

try:
    import rclpy
    from geometry_msgs.msg import PoseWithCovarianceStamped
    from nav_msgs.msg import OccupancyGrid, Odometry
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSDurabilityPolicy, QoSProfile, QoSReliabilityPolicy
    from sensor_msgs.msg import LaserScan
except ImportError:  # pragma: no cover - only happens outside ROS runtime
    rclpy = None
    PoseWithCovarianceStamped = None
    OccupancyGrid = None
    Odometry = None
    SingleThreadedExecutor = None
    QoSDurabilityPolicy = None
    QoSProfile = None
    QoSReliabilityPolicy = None
    LaserScan = None

from apps.ros_bridge.publishers.cmd_vel import RosRuntimeUnavailableError


class SlamMapSubscriber:
    def __init__(
        self,
        map_topic: str = "/map",
        odom_topic: str = "/odom",
        amcl_topic: str = "/amcl_pose",
        scan_topic: str = "/scan",
        scan_x_offset: float = -0.0455,
        scan_y_offset: float = 5.258e-05,
        scan_yaw_offset: float = 0.0,
        node_name: str = "ros_bridge_slam_map",
    ) -> None:
        if (
            rclpy is None
            or PoseWithCovarianceStamped is None
            or OccupancyGrid is None
            or Odometry is None
            or LaserScan is None
            or SingleThreadedExecutor is None
            or QoSDurabilityPolicy is None
            or QoSProfile is None
            or QoSReliabilityPolicy is None
        ):
            raise RosRuntimeUnavailableError(
                "ROS 2 Python runtime is unavailable. Please source the ROS 2 environment on the robot first."
            )

        self.map_topic = map_topic
        self.odom_topic = odom_topic
        self.amcl_topic = amcl_topic
        self.scan_topic = scan_topic
        self.scan_x_offset = float(scan_x_offset)
        self.scan_y_offset = float(scan_y_offset)
        self.scan_yaw_offset = float(scan_yaw_offset)
        self.node_name = node_name
        self._lock = threading.Lock()
        self._closed = False
        self._owns_rclpy_context = False
        self._latest_map: Optional[Dict[str, Any]] = None
        self._latest_pose: Optional[Dict[str, float]] = None
        self._latest_odom_pose: Optional[Dict[str, float]] = None
        self._latest_scan_points: list[Dict[str, float]] = []

        if not rclpy.ok():
            rclpy.init()
            self._owns_rclpy_context = True

        self._node = rclpy.create_node(node_name)
        map_qos = QoSProfile(depth=1)
        map_qos.reliability = QoSReliabilityPolicy.RELIABLE
        map_qos.durability = QoSDurabilityPolicy.TRANSIENT_LOCAL
        self._node.create_subscription(OccupancyGrid, map_topic, self._on_map, map_qos)
        self._node.create_subscription(Odometry, odom_topic, self._on_odom, 10)
        self._node.create_subscription(PoseWithCovarianceStamped, amcl_topic, self._on_amcl_pose, 10)
        self._node.create_subscription(LaserScan, scan_topic, self._on_scan, 10)
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._spin_thread.start()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            if self._latest_map is None:
                return {
                    "available": False,
                    "width": 0,
                    "height": 0,
                    "resolution": 0.0,
                    "origin": {"x": 0.0, "y": 0.0, "yaw": 0.0},
                    "robot_pose": self._latest_pose,
                    "data": [],
                }

            payload = dict(self._latest_map)
            payload["robot_pose"] = self._latest_pose
            payload["laser_points"] = list(self._latest_scan_points)
            return payload

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown()
        self._node.destroy_node()
        if self._owns_rclpy_context and rclpy.ok():
            rclpy.shutdown()

    def _on_map(self, msg: Any) -> None:
        info = msg.info
        origin_pose = info.origin
        snapshot = {
            "available": True,
            "frame_id": msg.header.frame_id,
            "stamp_sec": int(msg.header.stamp.sec),
            "stamp_nanosec": int(msg.header.stamp.nanosec),
            "width": int(info.width),
            "height": int(info.height),
            "resolution": float(info.resolution),
            "origin": {
                "x": float(origin_pose.position.x),
                "y": float(origin_pose.position.y),
                "yaw": _yaw_from_quaternion(origin_pose.orientation),
            },
            "data": list(msg.data),
        }
        with self._lock:
            self._latest_map = snapshot

    def _on_odom(self, msg: Any) -> None:
        pose = msg.pose.pose
        latest_pose = {
            "x": float(pose.position.x),
            "y": float(pose.position.y),
            "yaw": _yaw_from_quaternion(pose.orientation),
        }
        with self._lock:
            self._latest_odom_pose = latest_pose
            if self._latest_pose is None:
                self._latest_pose = latest_pose

    def _on_amcl_pose(self, msg: Any) -> None:
        pose = msg.pose.pose
        latest_pose = {
            "x": float(pose.position.x),
            "y": float(pose.position.y),
            "yaw": _yaw_from_quaternion(pose.orientation),
        }
        with self._lock:
            self._latest_pose = latest_pose

    def _on_scan(self, msg: Any) -> None:
        with self._lock:
            pose = self._latest_pose or self._latest_odom_pose
        if pose is None:
            return

        points: list[Dict[str, float]] = []
        ranges = list(msg.ranges)
        if not ranges:
            return

        step = max(1, len(ranges) // 360)
        robot_x = pose["x"]
        robot_y = pose["y"]
        robot_yaw = pose["yaw"]
        angle = float(msg.angle_min)
        increment = float(msg.angle_increment)
        range_min = float(msg.range_min)
        range_max = float(msg.range_max)

        for idx in range(0, len(ranges), step):
            distance = float(ranges[idx])
            if not math.isfinite(distance):
                continue
            if distance < range_min or distance > range_max:
                continue

            scan_theta = angle + increment * idx
            base_x = self.scan_x_offset + math.cos(self.scan_yaw_offset + scan_theta) * distance
            base_y = self.scan_y_offset + math.sin(self.scan_yaw_offset + scan_theta) * distance
            points.append(
                {
                    "x": robot_x + math.cos(robot_yaw) * base_x - math.sin(robot_yaw) * base_y,
                    "y": robot_y + math.sin(robot_yaw) * base_x + math.cos(robot_yaw) * base_y,
                }
            )

        with self._lock:
            self._latest_scan_points = points


def _yaw_from_quaternion(q: Any) -> float:
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)
