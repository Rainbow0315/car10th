from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

import httpx
from fastapi import HTTPException, status

from common.config.settings import settings


class InspectionService:
    def __init__(self) -> None:
        self._timeout = httpx.Timeout(300.0, connect=5.0)

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health")

    def detect_image(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/inspection/detect-image", json=payload)

    def detect_plate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/inspection/detect-plate", json=payload)

    def detect_ros_image(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/inspection/detect-ros-image", json=payload)

    def detect_ros_plate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/inspection/detect-ros-plate", json=payload)

    def camera_snapshot(self, topic_name: str, timeout_sec: float) -> Tuple[bytes, str]:
        url = f"{settings.ai_service_http_url.rstrip('/')}/api/camera/snapshot"
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout_sec + 5.0, connect=5.0)) as client:
                response = client.get(
                    url,
                    params={"topic_name": topic_name, "timeout_sec": timeout_sec},
                )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI service camera snapshot is unreachable at {settings.ai_service_http_url}: {exc}",
            ) from exc

        if response.is_success:
            return response.content, response.headers.get("content-type", "image/jpeg")

        try:
            body = response.json()
        except ValueError:
            detail: Any = response.text or f"ai_service returned HTTP {response.status_code}"
        else:
            detail = body.get("detail", body)
        raise HTTPException(status_code=response.status_code, detail=detail)

    def camera_status(self) -> Dict[str, Any]:
        return self._request("GET", "/api/camera/status")

    def camera_mjpeg_stream(self, topic_name: str, fps: float, timeout_sec: float) -> Iterator[bytes]:
        url = f"{settings.ai_service_http_url.rstrip('/')}/api/camera/mjpeg"
        timeout = httpx.Timeout(None, connect=5.0)
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream(
                    "GET",
                    url,
                    params={
                        "topic_name": topic_name,
                        "fps": fps,
                        "timeout_sec": timeout_sec,
                    },
                ) as response:
                    if response.status_code < 200 or response.status_code >= 300:
                        try:
                            detail: Any = response.json().get("detail")
                        except ValueError:
                            detail = response.text or f"ai_service returned HTTP {response.status_code}"
                        raise HTTPException(status_code=response.status_code, detail=detail)
                    for chunk in response.iter_bytes():
                        if chunk:
                            yield chunk
        except HTTPException:
            raise
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI service MJPEG stream is unreachable at {settings.ai_service_http_url}: {exc}",
            ) from exc

    def download_frame(self, image_path: str, output_dir: str) -> Optional[str]:
        if not image_path:
            return None
        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        target = output_root / Path(image_path).name
        url = f"{settings.ai_service_http_url.rstrip('/')}/api/inspection/frame"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url, params={"image_path": image_path})
                response.raise_for_status()
        except httpx.HTTPError:
            return None
        target.write_bytes(response.content)
        return str(target)

    def fetch_frame_bytes(self, image_path: str) -> Optional[Tuple[bytes, str]]:
        if not image_path:
            return None
        url = f"{settings.ai_service_http_url.rstrip('/')}/api/inspection/frame"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url, params={"image_path": image_path})
                response.raise_for_status()
        except httpx.HTTPError:
            return None
        return response.content, response.headers.get("content-type", "image/jpeg")

    def upload_frame_to_cloud(self, image_path: str) -> Optional[Dict[str, Any]]:
        if not settings.inspection_cloud_frame_upload_enabled:
            return None
        fetched = self.fetch_frame_bytes(image_path)
        if fetched is None:
            return None
        content, content_type = fetched
        filename = Path(image_path).name
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    settings.inspection_cloud_frame_upload_url,
                    json={
                        "filename": filename,
                        "content_base64": base64.b64encode(content).decode("ascii"),
                        "content_type": content_type,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError:
            return None
        return response.json()

    def delete_frame(self, image_path: str) -> bool:
        if not image_path:
            return False
        url = f"{settings.ai_service_http_url.rstrip('/')}/api/inspection/frame"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.delete(url, params={"image_path": image_path})
        except httpx.HTTPError:
            return False
        return response.is_success

    def _request(self, method: str, path: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{settings.ai_service_http_url.rstrip('/')}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.request(method, url, json=json)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI service is unreachable at {settings.ai_service_http_url}: {exc}",
            ) from exc

        if response.is_success:
            return response.json()

        try:
            body = response.json()
        except ValueError:
            detail: Any = response.text or f"ai_service returned HTTP {response.status_code}"
        else:
            detail = body.get("detail", body)

        raise HTTPException(status_code=response.status_code, detail=detail)


inspection_service = InspectionService()
