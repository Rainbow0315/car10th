from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from common.config.settings import settings
from apps.web_api.services.mqtt_service import mqtt_service
from common.models.entities import AlarmLog, AlarmStatus, AlarmType, RiskLevel
from common.schemas.inspection import AlarmLogResponse
from common.schemas.robot import AlarmNotifyPayload


class InspectionAlarmService:
    def create_alarms_from_result(
        self,
        db: Session,
        result: Dict[str, Any],
        *,
        publish_mqtt: bool = True,
    ) -> List[AlarmLog]:
        summary = result.get("summary") or {}
        if not summary.get("has_risk"):
            return []

        image_path = str(result.get("image_path") or "")
        image_url = str(result.get("image_url") or "") or None
        robot_code = str(result.get("robot_code") or "robot_001")
        camera_code = result.get("camera_code")
        detected_at = self._parse_datetime(result.get("detected_at"))

        alarms: List[AlarmLog] = []
        seen_dedup_keys = set()
        for model_name, detector_result in (result.get("results") or {}).items():
            if not isinstance(detector_result, dict) or detector_result.get("error"):
                continue
            for detection in detector_result.get("detections") or []:
                confidence = self._confidence(detection)
                if confidence < settings.inspection_alarm_min_confidence:
                    continue
                alarm = self._build_alarm(
                    image_path=image_path,
                    image_url=image_url,
                    robot_code=robot_code,
                    camera_code=camera_code,
                    detected_at=detected_at,
                    model_name=str(model_name),
                    detection=detection,
                )
                if alarm.dedup_key in seen_dedup_keys or self._has_recent_duplicate(db, alarm):
                    continue
                seen_dedup_keys.add(alarm.dedup_key)
                db.add(alarm)
                alarms.append(alarm)

        if not alarms:
            self.remove_frame(image_path)
            return []

        db.commit()
        for alarm in alarms:
            db.refresh(alarm)
            if publish_mqtt:
                pushed = self.publish_alarm(alarm)
                if pushed:
                    alarm.mqtt_pushed = 1

        db.commit()
        for alarm in alarms:
            db.refresh(alarm)
        return alarms

    def list_alarms(
        self,
        db: Session,
        *,
        status: Optional[str] = None,
        alarm_type: Optional[str] = None,
        risk_level: Optional[str] = None,
        limit: int = 50,
    ) -> List[AlarmLog]:
        query = db.query(AlarmLog)
        query = query.filter(AlarmLog.confidence >= settings.inspection_alarm_min_confidence)
        if status:
            query = query.filter(AlarmLog.status == self._parse_enum(AlarmStatus, status, "status"))
        if alarm_type:
            query = query.filter(AlarmLog.alarm_type == self._parse_enum(AlarmType, alarm_type, "alarm_type"))
        if risk_level:
            query = query.filter(AlarmLog.risk_level == self._parse_enum(RiskLevel, risk_level, "risk_level"))
        return query.order_by(AlarmLog.detected_at.desc()).limit(limit).all()

    def get_alarm(self, db: Session, alarm_id_or_no: str) -> Optional[AlarmLog]:
        if alarm_id_or_no.isdigit():
            alarm = db.query(AlarmLog).filter(AlarmLog.id == int(alarm_id_or_no)).first()
            if alarm:
                return alarm
        return db.query(AlarmLog).filter(AlarmLog.alarm_no == alarm_id_or_no).first()

    def mark_handled(self, db: Session, alarm_id_or_no: str, remark: str) -> Optional[AlarmLog]:
        alarm = self.get_alarm(db, alarm_id_or_no)
        if alarm is None:
            return None
        alarm.status = AlarmStatus.closed
        alarm.handled_at = datetime.now()
        alarm.handle_remark = remark.strip() or None
        db.commit()
        db.refresh(alarm)
        return alarm

    def publish_alarm(self, alarm: AlarmLog) -> bool:
        payload = AlarmNotifyPayload(
            alarm_id=alarm.id,
            alarm_no=alarm.alarm_no,
            robot_code=alarm.robot_code,
            camera_code=alarm.camera_code,
            alarm_type=alarm.alarm_type.value,
            risk_level=alarm.risk_level.value,
            confidence=float(alarm.confidence),
            detection_model=alarm.detection_model,
            detection_label=alarm.detection_label,
            bbox=[float(v) for v in (alarm.bbox_json or [])],
            image_path=alarm.image_path,
            image_url=alarm.image_url,
            pos_x=float(alarm.pos_x),
            pos_y=float(alarm.pos_y),
            detected_at=alarm.detected_at,
            description=self._description(alarm),
        )
        return mqtt_service.publish_alarm(payload)

    def to_response(self, alarm: AlarmLog) -> AlarmLogResponse:
        return AlarmLogResponse(
            id=alarm.id,
            alarm_no=alarm.alarm_no,
            alarm_type=alarm.alarm_type.value,
            risk_level=alarm.risk_level.value,
            status=alarm.status.value,
            confidence=float(alarm.confidence),
            robot_code=alarm.robot_code,
            camera_code=alarm.camera_code,
            image_path=alarm.image_path,
            image_url=alarm.image_url,
            pos_x=float(alarm.pos_x),
            pos_y=float(alarm.pos_y),
            pos_yaw=float(alarm.pos_yaw) if alarm.pos_yaw is not None else None,
            map_name=alarm.map_name,
            detection_model=alarm.detection_model,
            detection_label=alarm.detection_label,
            bbox=[float(v) for v in (alarm.bbox_json or [])],
            raw_result=alarm.raw_result or {},
            detected_at=alarm.detected_at,
            mqtt_pushed=bool(alarm.mqtt_pushed),
            handle_remark=alarm.handle_remark,
        )

    def remove_non_risk_frame(self, result: Dict[str, Any]) -> None:
        summary = result.get("summary") or {}
        if summary.get("has_risk"):
            return
        image_path = result.get("image_path")
        self.remove_frame(image_path)

    def remove_frame(self, image_path: Any) -> None:
        if not image_path:
            return
        try:
            Path(str(image_path)).unlink(missing_ok=True)
        except OSError:
            pass

    def _build_alarm(
        self,
        *,
        image_path: str,
        image_url: Optional[str],
        robot_code: str,
        camera_code: Optional[str],
        detected_at: datetime,
        model_name: str,
        detection: Dict[str, Any],
    ) -> AlarmLog:
        label = str(detection.get("label") or model_name)
        confidence = self._confidence(detection)
        bbox = self._bbox(detection.get("bbox") or [])
        alarm_type = self._alarm_type(model_name=model_name, label=label)
        risk_level = self._risk_level(confidence=confidence, detection=detection)
        dedup_key = self._dedup_key(
            alarm_type=alarm_type,
            robot_code=robot_code,
            camera_code=camera_code,
            bbox=bbox,
            detected_at=detected_at,
        )

        return AlarmLog(
            alarm_no=self._alarm_no(alarm_type=alarm_type, detected_at=detected_at, dedup_key=dedup_key),
            alarm_type=alarm_type,
            risk_level=risk_level,
            confidence=Decimal(str(round(max(0.0, min(1.0, confidence)), 4))),
            robot_code=robot_code,
            camera_code=camera_code,
            image_path=image_path,
            image_url=image_url,
            detection_model=model_name,
            detection_label=label,
            bbox_json=bbox,
            raw_result=detection,
            pos_x=0.0,
            pos_y=0.0,
            pos_yaw=None,
            map_name=None,
            status=AlarmStatus.pending,
            dedup_key=dedup_key,
            detected_at=detected_at,
            mqtt_pushed=0,
        )

    def _alarm_type(self, *, model_name: str, label: str) -> AlarmType:
        value = f"{model_name} {label}".lower()
        if "crack" in value or "裂缝" in value or "破损" in value:
            return AlarmType.crack
        if "puddle" in value or "water" in value or "积水" in value or "水洼" in value:
            return AlarmType.water
        if (
            "fod" in value
            or "foreign" in value
            or "debris" in value
            or "异物" in value
            or "障碍" in value
            or "垃圾" in value
        ):
            return AlarmType.foreign_object
        if "pothole" in value or "坑" in value:
            return AlarmType.pothole
        return AlarmType.other

    def _risk_level(self, *, confidence: float, detection: Dict[str, Any]) -> RiskLevel:
        extra = detection.get("extra") or {}
        severity = str(extra.get("severity") or "").lower()
        if severity in {"high", "serious", "severe"}:
            return RiskLevel.high
        if severity in {"medium", "moderate"}:
            return RiskLevel.medium
        if confidence >= 0.75:
            return RiskLevel.high
        if confidence >= 0.5:
            return RiskLevel.medium
        return RiskLevel.low

    def _confidence(self, detection: Dict[str, Any]) -> float:
        try:
            return float(detection.get("confidence") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _bbox(self, values: Iterable[Any]) -> List[float]:
        bbox = []
        for value in values:
            try:
                bbox.append(float(value))
            except (TypeError, ValueError):
                continue
        return bbox[:4]

    def _parse_datetime(self, raw: Any) -> datetime:
        if isinstance(raw, datetime):
            return raw.replace(tzinfo=None)
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                pass
        return datetime.now()

    def _has_recent_duplicate(self, db: Session, alarm: AlarmLog) -> bool:
        since = alarm.detected_at - timedelta(seconds=60)
        return (
            db.query(AlarmLog.id)
            .filter(
                AlarmLog.dedup_key == alarm.dedup_key,
                AlarmLog.detected_at >= since,
            )
            .first()
            is not None
        )

    def _parse_enum(self, enum_type: Any, raw: str, field_name: str) -> Any:
        try:
            return enum_type(raw)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in enum_type)
            raise ValueError(f"invalid {field_name}: {raw}. allowed: {allowed}") from exc

    def _alarm_no(self, *, alarm_type: AlarmType, detected_at: datetime, dedup_key: str) -> str:
        suffix = hashlib.sha1(f"{alarm_type.value}:{detected_at.timestamp()}:{dedup_key}".encode()).hexdigest()[:6]
        return f"ALM{detected_at.strftime('%Y%m%d%H%M%S%f')[:-3]}{suffix}"

    def _dedup_key(
        self,
        *,
        alarm_type: AlarmType,
        robot_code: str,
        camera_code: Optional[str],
        bbox: List[float],
        detected_at: datetime,
    ) -> str:
        minute = detected_at.strftime("%Y%m%d%H%M")
        grid = ",".join(str(round(v / 20) * 20) for v in bbox[:4])
        raw = f"{alarm_type.value}:{robot_code}:{camera_code or ''}:{grid}:{minute}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _description(self, alarm: AlarmLog) -> str:
        label = alarm.detection_label or alarm.alarm_type.value
        return f"{alarm.robot_code} detected {label} ({alarm.risk_level.value})"


inspection_alarm_service = InspectionAlarmService()
