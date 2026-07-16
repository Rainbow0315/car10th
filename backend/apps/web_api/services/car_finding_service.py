from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException, status

from apps.web_api.services.inspection_service import inspection_service
from apps.web_api.services.slam_service import slam_service
from common.config.settings import settings


GENERIC_PLATE_LABELS = {"plate", "licenseplate", "licenceplate", "carplate", "vehicleplate"}


class CarFindingService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._bindings: Dict[str, Dict[str, Any]] = {}
        self._parking_records: Dict[str, Dict[str, Any]] = {}

    def parking_spots(self) -> List[Dict[str, Any]]:
        return [self._spot_one()]

    def bind_plate(self, user_id: str, plate_number: str) -> Dict[str, Any]:
        normalized = self.normalize_plate(plate_number)
        if not normalized:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="plate_number is empty")
        item = {
            "user_id": user_id,
            "plate_number": plate_number.strip(),
            "normalized_plate_number": normalized,
            "updated_at": self._now(),
        }
        with self._lock:
            self._bindings[user_id] = item
        return dict(item)

    def park_at_spot_one(self, user_id: str, plate_number: Optional[str] = None) -> Dict[str, Any]:
        if plate_number:
            binding = self.bind_plate(user_id, plate_number)
        else:
            binding = self._require_binding(user_id)
        spot = self._spot_one()
        record = {
            "user_id": user_id,
            "spot_id": spot["spot_id"],
            "spot_name": spot["name"],
            "plate_number": binding["plate_number"],
            "normalized_plate_number": binding["normalized_plate_number"],
            "pose": dict(spot["pose"]),
            "recorded_at": self._now(),
        }
        with self._lock:
            self._parking_records[user_id] = record
        return dict(record)

    def guide_to_spot_one(self, user_id: str) -> Dict[str, Any]:
        record = self._require_parking_record(user_id)
        spot = self._spot_one()
        pose = spot["pose"]
        nav_goal = slam_service.publish_goal(
            {
                "x": pose["x"],
                "y": pose["y"],
                "yaw": pose["yaw"],
                "frame_id": pose["frame_id"],
            }
        )
        return {
            "user_id": user_id,
            "spot": spot,
            "parking_record": record,
            "nav_goal": nav_goal,
        }

    def verify_at_spot_one(
        self,
        user_id: str,
        topic_name: str,
        timeout_sec: float,
        robot_code: str,
        camera_code: Optional[str],
    ) -> Dict[str, Any]:
        record = self._require_parking_record(user_id)
        detection = inspection_service.detect_ros_plate(
            {
                "topic_name": topic_name,
                "timeout_sec": timeout_sec,
                "robot_code": robot_code,
                "camera_code": camera_code,
                "enabled_models": ["plate"],
            }
        )
        detected_plates = self.extract_plate_candidates(detection)
        normalized_detected = [self.normalize_plate(item) for item in detected_plates]
        normalized_detected = [item for item in normalized_detected if item]
        expected = str(record["normalized_plate_number"])
        return {
            "user_id": user_id,
            "matched": expected in normalized_detected,
            "expected_plate": record["plate_number"],
            "expected_normalized_plate": expected,
            "detected_plates": detected_plates,
            "detected_normalized_plates": normalized_detected,
            "parking_record": record,
            "detection": detection,
        }

    def verify_plate(
        self,
        plate_number: str,
        topic_name: str,
        timeout_sec: float,
        robot_code: str,
        camera_code: Optional[str],
    ) -> Dict[str, Any]:
        expected = self.normalize_plate(plate_number)
        if not expected:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="plate_number is empty")
        detection = inspection_service.detect_ros_plate(
            {
                "topic_name": topic_name,
                "timeout_sec": timeout_sec,
                "robot_code": robot_code,
                "camera_code": camera_code,
                "enabled_models": ["plate"],
            }
        )
        detected_plates = self.extract_plate_candidates(detection)
        normalized_detected = [self.normalize_plate(item) for item in detected_plates]
        normalized_detected = [item for item in normalized_detected if item]
        return {
            "matched": expected in normalized_detected,
            "expected_plate": plate_number.strip(),
            "expected_normalized_plate": expected,
            "detected_plates": detected_plates,
            "detected_normalized_plates": normalized_detected,
            "detection": detection,
        }

    @staticmethod
    def normalize_plate(value: Any) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).upper()
        return re.sub(r"[^0-9A-Z\u4E00-\u9FFF]", "", text)

    def extract_plate_candidates(self, detection: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        results = detection.get("results") or {}
        if isinstance(results, dict):
            for result in results.values():
                if not isinstance(result, dict):
                    continue
                for item in result.get("detections") or []:
                    candidates.extend(self._candidate_values_from_detection(item))
        return self._unique_candidates(candidates)

    def _candidate_values_from_detection(self, item: Any) -> Iterable[str]:
        if not isinstance(item, dict):
            return []
        values: List[str] = []
        label = item.get("label")
        if isinstance(label, str) and self._looks_like_plate_text(label):
            values.append(label)
        extra = item.get("extra") or {}
        if isinstance(extra, dict):
            for key in ("plate_number", "plate_text", "license_plate", "text", "number", "plate"):
                value = extra.get(key)
                if isinstance(value, str) and self._looks_like_plate_text(value):
                    values.append(value)
            values.extend(self._walk_extra_for_plate_text(extra))
        return values

    def _walk_extra_for_plate_text(self, value: Any, key_hint: str = "") -> Iterable[str]:
        if isinstance(value, dict):
            values: List[str] = []
            for key, item in value.items():
                values.extend(self._walk_extra_for_plate_text(item, str(key)))
            return values
        if isinstance(value, list):
            values = []
            for item in value:
                values.extend(self._walk_extra_for_plate_text(item, key_hint))
            return values
        normalized_key = self.normalize_plate(key_hint).lower()
        key_suggests_plate = any(token in normalized_key for token in ("plate", "text", "number"))
        if key_suggests_plate and isinstance(value, str) and self._looks_like_plate_text(value):
            return [value]
        return []

    def _looks_like_plate_text(self, value: str) -> bool:
        normalized = self.normalize_plate(value)
        if len(normalized) < 4:
            return False
        return normalized.lower() not in GENERIC_PLATE_LABELS

    def _unique_candidates(self, candidates: Iterable[str]) -> List[str]:
        seen = set()
        unique = []
        for item in candidates:
            normalized = self.normalize_plate(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(item)
        return unique

    def _require_binding(self, user_id: str) -> Dict[str, Any]:
        with self._lock:
            binding = self._bindings.get(user_id)
        if binding is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"plate binding not found: {user_id}")
        return dict(binding)

    def _require_parking_record(self, user_id: str) -> Dict[str, Any]:
        with self._lock:
            record = self._parking_records.get(user_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"parking record not found: {user_id}")
        return dict(record)

    def _spot_one(self) -> Dict[str, Any]:
        return {
            "spot_id": "spot_1",
            "name": "车位一",
            "pose": {
                "x": settings.parking_spot_one_x,
                "y": settings.parking_spot_one_y,
                "yaw": settings.parking_spot_one_yaw,
                "frame_id": settings.parking_spot_one_frame_id,
            },
        }

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


car_finding_service = CarFindingService()
