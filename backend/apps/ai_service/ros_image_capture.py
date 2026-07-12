from __future__ import annotations

import time
from pathlib import Path
from typing import Dict

try:
    import cv2
    import numpy as np
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import Image as RosImage
except ImportError:  # pragma: no cover - only happens outside ROS runtime
    cv2 = None
    np = None
    rclpy = None
    SingleThreadedExecutor = None
    DurabilityPolicy = None
    HistoryPolicy = None
    QoSProfile = None
    ReliabilityPolicy = None
    RosImage = None


class RosImageCaptureError(RuntimeError):
    pass


class RosImageCaptureService:
    def capture_single_frame(self, *, topic_name: str, output_path: Path, timeout_sec: float, node_name: str) -> Dict[str, str]:
        if (
            cv2 is None
            or np is None
            or rclpy is None
            or SingleThreadedExecutor is None
            or QoSProfile is None
            or RosImage is None
        ):
            raise RosImageCaptureError("ROS 2 Python runtime or OpenCV is unavailable. Please source the robot ROS environment first.")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload: Dict[str, str] = {}
        owns_rclpy_context = False
        if not rclpy.ok():
            rclpy.init()
            owns_rclpy_context = True

        node = rclpy.create_node(node_name)
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        subscription = None

        try:
            qos = QoSProfile(
                depth=5,
                history=HistoryPolicy.KEEP_LAST,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )

            def callback(msg: RosImage) -> None:
                if payload:
                    return
                try:
                    image = self._to_bgr_image(msg)
                    if not cv2.imwrite(str(output_path), image):
                        raise RosImageCaptureError(f"无法写入抓帧图片: {output_path}")
                    payload.update(
                        {
                            "image_path": str(output_path),
                            "encoding": msg.encoding,
                            "width": str(msg.width),
                            "height": str(msg.height),
                        }
                    )
                except Exception as exc:  # pragma: no cover - runtime branch
                    payload["error"] = str(exc)

            subscription = node.create_subscription(RosImage, topic_name, callback, qos)

            deadline = time.monotonic() + max(0.5, timeout_sec)
            while time.monotonic() < deadline and not payload:
                executor.spin_once(timeout_sec=0.1)

            if not payload:
                raise RosImageCaptureError(f"在 {timeout_sec:.1f}s 内未从 topic `{topic_name}` 收到图像帧")
            if "error" in payload:
                raise RosImageCaptureError(payload["error"])
            return payload
        finally:
            if subscription is not None:
                node.destroy_subscription(subscription)
            executor.shutdown()
            node.destroy_node()
            if owns_rclpy_context and rclpy.ok():
                rclpy.shutdown()

    def _to_bgr_image(self, msg: RosImage):
        encoding = str(msg.encoding or "").lower()
        if encoding not in {"bgr8", "rgb8", "bgra8", "rgba8", "mono8"}:
            raise RosImageCaptureError(f"暂不支持的图像编码: {msg.encoding}")

        channels = {"mono8": 1, "bgr8": 3, "rgb8": 3, "bgra8": 4, "rgba8": 4}[encoding]
        row = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.step))
        trimmed = row[:, : msg.width * channels]

        if channels == 1:
            image = trimmed.reshape((msg.height, msg.width))
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        image = trimmed.reshape((msg.height, msg.width, channels))
        if encoding == "bgr8":
            return image
        if encoding == "rgb8":
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        if encoding == "bgra8":
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)


ros_image_capture_service = RosImageCaptureService()
