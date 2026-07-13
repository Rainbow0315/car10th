from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status

from common.config.settings import settings


class SlamService:
    def __init__(self) -> None:
        self._timeout = httpx.Timeout(8.0, connect=2.0)

    def get_map(self) -> Dict[str, Any]:
        return self._request("GET", "/api/slam/map")

    def publish_goal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/slam/goal", json=payload)

    def publish_initial_pose(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/slam/initial-pose", json=payload)

    def _request(self, method: str, path: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{settings.ros_bridge_http_url.rstrip('/')}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.request(method, url, json=json)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"ROS bridge is unreachable at {settings.ros_bridge_http_url}: {exc}",
            ) from exc

        if response.is_success:
            return response.json()

        try:
            body = response.json()
        except ValueError:
            detail: Any = response.text or f"ros_bridge returned HTTP {response.status_code}"
        else:
            detail = body.get("detail", body)

        raise HTTPException(status_code=response.status_code, detail=detail)


slam_service = SlamService()
