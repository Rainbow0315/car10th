from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status

from common.config.settings import settings


class InspectionService:
    def __init__(self) -> None:
        self._timeout = httpx.Timeout(30.0, connect=5.0)

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health")

    def detect_image(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/inspection/detect-image", json=payload)

    def detect_plate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/inspection/detect-plate", json=payload)

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
