from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

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


@dataclass
class CachedFrame:
    image: Any
    encoding: str
    width: int
    height: int
    received_at: float


class RosImageCaptureService:
    """Keep one ROS image subscription alive and serve the latest frame to all callers."""

    def __init__(self) -> None:
        self._state_lock = threading.RLock()
        self._subscription_lock = threading.Lock()
        self._frame_event = threading.Event()
        self._topic_name: str | None = None
        self._node = None
        self._executor = None
        self._subscription = None
        self._spin_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._owns_rclpy_context = False
        self._latest_frame: CachedFrame | None = None
        self._last_error: str | None = None
        self._status_fresh_age_sec = 2.0

    def capture_single_frame(self, *, topic_name: str, output_path: Path, timeout_sec: float, node_name: str) -> Dict[str, str]:
        # Keep the public method name for existing callers, but use the shared cache internally.
        return self.save_latest_frame(
            topic_name=topic_name,
            output_path=output_path,
            timeout_sec=timeout_sec,
            node_name=node_name,
        )

    def save_latest_frame(
        self,
        *,
        topic_name: str,
        output_path: Path,
        timeout_sec: float,
        node_name: str = "ai_service_image_cache",
    ) -> Dict[str, str]:
        frame = self.get_latest_frame(topic_name=topic_name, timeout_sec=timeout_sec, node_name=node_name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output_path), frame.image):
            raise RosImageCaptureError(f"failed to write captured frame: {output_path}")
        return {
            "image_path": str(output_path),
            "encoding": frame.encoding,
            "width": str(frame.width),
            "height": str(frame.height),
            "received_at": f"{frame.received_at:.6f}",
        }

    def latest_jpeg(
        self,
        *,
        topic_name: str,
        timeout_sec: float,
        node_name: str = "ai_service_image_cache",
        jpeg_quality: int = 85,
    ) -> tuple[bytes, Dict[str, str]]:
        frame = self.get_latest_frame(topic_name=topic_name, timeout_sec=timeout_sec, node_name=node_name)
        ok, encoded = cv2.imencode(".jpg", frame.image, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)])
        if not ok:
            raise RosImageCaptureError("failed to encode cached frame as JPEG")
        return (
            encoded.tobytes(),
            {
                "encoding": frame.encoding,
                "width": str(frame.width),
                "height": str(frame.height),
                "received_at": f"{frame.received_at:.6f}",
                "topic_name": topic_name,
            },
        )

    def get_latest_frame(self, *, topic_name: str, timeout_sec: float, node_name: str) -> CachedFrame:
        self._ensure_runtime()
        self._ensure_subscription(topic_name=topic_name, node_name=node_name)

        deadline = time.monotonic() + max(0.5, timeout_sec)
        max_frame_age_sec = min(2.0, max(0.5, timeout_sec))
        while time.monotonic() < deadline:
            with self._state_lock:
                if (
                    self._latest_frame is not None
                    and self._topic_name == topic_name
                    and time.monotonic() - self._latest_frame.received_at <= max_frame_age_sec
                ):
                    return CachedFrame(
                        image=self._latest_frame.image.copy(),
                        encoding=self._latest_frame.encoding,
                        width=self._latest_frame.width,
                        height=self._latest_frame.height,
                        received_at=self._latest_frame.received_at,
                    )
                if self._last_error:
                    raise RosImageCaptureError(self._last_error)

            remaining = max(0.0, deadline - time.monotonic())
            self._frame_event.wait(timeout=min(0.1, remaining))
            self._frame_event.clear()

        raise RosImageCaptureError(f"no fresh image frame received from topic `{topic_name}` within {timeout_sec:.1f}s")

    def status(self) -> Dict[str, Any]:
        with self._state_lock:
            frame_age_sec = None
            frame_is_fresh = False
            if self._latest_frame is not None:
                frame_age_sec = max(0.0, time.monotonic() - self._latest_frame.received_at)
                frame_is_fresh = frame_age_sec <= self._status_fresh_age_sec
            return {
                "running": self._spin_thread is not None and self._spin_thread.is_alive(),
                "topic_name": self._topic_name,
                "has_frame": self._latest_frame is not None,
                "frame_age_sec": frame_age_sec,
                "frame_is_fresh": frame_is_fresh,
                "last_error": self._last_error,
            }

    def shutdown(self) -> None:
        with self._state_lock:
            thread = self._spin_thread
            executor = self._executor
            node = self._node
            owns_rclpy_context = self._owns_rclpy_context
            self._stop_event.set()

        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        with self._state_lock:
            if executor is not None:
                executor.shutdown()
            if node is not None:
                node.destroy_node()
            if owns_rclpy_context and rclpy is not None and rclpy.ok():
                rclpy.shutdown()
            self._topic_name = None
            self._node = None
            self._executor = None
            self._subscription = None
            self._spin_thread = None
            self._stop_event = threading.Event()
            self._owns_rclpy_context = False
            self._latest_frame = None
            self._last_error = None

    def _ensure_subscription(self, *, topic_name: str, node_name: str) -> None:
        with self._subscription_lock:
            with self._state_lock:
                if (
                    self._topic_name == topic_name
                    and self._spin_thread is not None
                    and self._spin_thread.is_alive()
                ):
                    return

            self.shutdown()

            with self._state_lock:
                if (
                    self._topic_name == topic_name
                    and self._spin_thread is not None
                    and self._spin_thread.is_alive()
                ):
                    return

                if not rclpy.ok():
                    rclpy.init()
                    self._owns_rclpy_context = True

                self._topic_name = topic_name
                self._latest_frame = None
                self._last_error = None
                self._frame_event.clear()
                self._stop_event.clear()

                qos = QoSProfile(
                    depth=5,
                    history=HistoryPolicy.KEEP_LAST,
                    reliability=ReliabilityPolicy.BEST_EFFORT,
                    durability=DurabilityPolicy.VOLATILE,
                )
                self._node = rclpy.create_node(node_name)
                self._executor = SingleThreadedExecutor()
                self._executor.add_node(self._node)
                self._subscription = self._node.create_subscription(RosImage, topic_name, self._on_image, qos)
                self._spin_thread = threading.Thread(
                    target=self._spin_loop,
                    name=f"ros-image-cache-{topic_name.strip('/').replace('/', '-') or 'image'}",
                    daemon=True,
                )
                self._spin_thread.start()

    def _spin_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._executor.spin_once(timeout_sec=0.1)
            except Exception as exc:  # pragma: no cover - runtime branch
                with self._state_lock:
                    self._last_error = str(exc)
                self._frame_event.set()
                time.sleep(0.2)

    def _on_image(self, msg: RosImage) -> None:
        try:
            image = self._to_bgr_image(msg).copy()
            frame = CachedFrame(
                image=image,
                encoding=str(msg.encoding or ""),
                width=int(msg.width),
                height=int(msg.height),
                received_at=time.monotonic(),
            )
            with self._state_lock:
                self._latest_frame = frame
                self._last_error = None
            self._frame_event.set()
        except Exception as exc:  # pragma: no cover - runtime branch
            with self._state_lock:
                self._last_error = str(exc)
            self._frame_event.set()

    def _ensure_runtime(self) -> None:
        if (
            cv2 is None
            or np is None
            or rclpy is None
            or SingleThreadedExecutor is None
            or QoSProfile is None
            or RosImage is None
        ):
            raise RosImageCaptureError("ROS 2 Python runtime or OpenCV is unavailable. Please source the robot ROS environment first.")

    def _to_bgr_image(self, msg: RosImage):
        encoding = str(msg.encoding or "").lower()
        if encoding in {"yuv422p", "yuv422", "yuyv", "yuyv422"}:
            row = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.step))
            packed = row[:, : msg.width * 2].reshape((msg.height, msg.width, 2))
            return cv2.cvtColor(packed, cv2.COLOR_YUV2BGR_YUY2)
        if encoding in {"uyvy", "uyvy422"}:
            row = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.step))
            packed = row[:, : msg.width * 2].reshape((msg.height, msg.width, 2))
            return cv2.cvtColor(packed, cv2.COLOR_YUV2BGR_UYVY)
        if encoding not in {"bgr8", "rgb8", "bgra8", "rgba8", "mono8"}:
            raise RosImageCaptureError(f"unsupported image encoding: {msg.encoding}")

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
