from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from apps.ai_service.detectors import CrackDetector, PlateDetector, YoloV7Detector
from apps.ai_service.ros_image_capture import ros_image_capture_service
from common.config.settings import settings
from common.schemas.inspection import (
    DetectorResult,
    ImageInspectionRequest,
    ImageInspectionResponse,
    InspectionSummary,
    RosTopicInspectionRequest,
)


class InspectionPipeline:
    _ROAD_MODEL_ALIASES = {"unified", "road", "road_inspection", "crack", "puddle", "fod"}
    _SUPPORTED_MODELS = {"unified", "crack", "puddle", "fod", "plate"}

    def __init__(self) -> None:
        self._detectors: Dict[str, object] = {}

    def inspect_image(self, request: ImageInspectionRequest) -> ImageInspectionResponse:
        image_path = self._resolve_image_path(request.image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"图片不存在: {image_path}")

        return self._run_detection(
            image_path=image_path,
            robot_code=request.robot_code,
            camera_code=request.camera_code,
            enabled_models=request.enabled_models,
        )

    def inspect_ros_topic(self, request: RosTopicInspectionRequest) -> ImageInspectionResponse:
        output_dir = self._resolve_output_dir(request.output_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        image_path = output_dir / f"ros_frame_{timestamp}.jpg"

        ros_image_capture_service.capture_single_frame(
            topic_name=request.topic_name,
            output_path=image_path,
            timeout_sec=request.timeout_sec,
            node_name="ai_service_ros_image_capture",
        )

        return self._run_detection(
            image_path=image_path,
            robot_code=request.robot_code,
            camera_code=request.camera_code,
            enabled_models=request.enabled_models,
        )

    def _run_detection(
        self,
        *,
        image_path: Path,
        robot_code: str,
        camera_code: str | None,
        enabled_models: Iterable[str],
    ) -> ImageInspectionResponse:
        if not image_path.exists():
            raise FileNotFoundError(f"图片不存在: {image_path}")

        enabled_models = self._normalize_models(enabled_models)
        results: Dict[str, DetectorResult] = {}
        labels: Dict[str, int] = {}
        completed_models: List[str] = []
        failed_models: List[str] = []
        total_detections = 0

        for model_name in enabled_models:
            try:
                detector = self._get_detector(model_name)
                detections = detector.detect(str(image_path))
                for item in detections:
                    labels[item["label"]] = labels.get(item["label"], 0) + 1
                total_detections += len(detections)
                completed_models.append(model_name)
                results[model_name] = DetectorResult(
                    model=model_name,
                    count=len(detections),
                    detections=detections,
                    error=None,
                )
            except Exception as exc:
                failed_models.append(model_name)
                results[model_name] = DetectorResult(
                    model=model_name,
                    count=0,
                    detections=[],
                    error=str(exc),
                )

        return ImageInspectionResponse(
            image_path=str(image_path),
            robot_code=robot_code,
            camera_code=camera_code,
            device=settings.inference_device,
            detected_at=datetime.now(),
            summary=InspectionSummary(
                total_detections=total_detections,
                has_risk=total_detections > 0,
                labels=labels,
                completed_models=completed_models,
                failed_models=failed_models,
            ),
            results=results,
        )

    def _resolve_image_path(self, image_path: str) -> Path:
        path = Path(image_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return path

    def _resolve_output_dir(self, output_dir: str | None) -> Path:
        raw = Path(output_dir).expanduser() if output_dir else Path(settings.inspection_output_dir) / "captured_frames"
        if not raw.is_absolute():
            raw = (Path.cwd() / raw).resolve()
        raw.mkdir(parents=True, exist_ok=True)
        return raw

    def _normalize_models(self, models: Iterable[str]) -> List[str]:
        normalized = []
        road_requested = False
        for model_name in models:
            value = str(model_name).strip().lower()
            if not value:
                continue
            if value in self._ROAD_MODEL_ALIASES:
                road_requested = True
                continue
            if value and value not in normalized:
                normalized.append(value)
        if road_requested:
            normalized.insert(0, "unified")
        return normalized or list(settings.default_enabled_models)

    def release_model(self, model_name: str) -> None:
        detector = self._detectors.pop(model_name, None)
        if detector is not None and hasattr(detector, "unload"):
            detector.unload()

    def _switch_mode(self, keep: str) -> None:
        for model_name in list(self._detectors.keys()):
            if model_name != keep:
                self.release_model(model_name)

    def _get_detector(self, model_name: str):
        if model_name in self._detectors:
            return self._detectors[model_name]

        if model_name not in self._SUPPORTED_MODELS:
            raise RuntimeError(f"不支持的模型: {model_name}")

        self._switch_mode(keep=model_name)

        if model_name == "unified":
            detector = CrackDetector(
                conf=settings.detection_conf,
                iou=settings.detection_iou,
                device=settings.inference_device,
                model_tag="unified",
            )
            detector.load_model(settings.model_unified)
        elif model_name == "crack":
            detector = CrackDetector(
                conf=settings.detection_conf,
                iou=settings.detection_iou,
                device=settings.inference_device,
            )
            detector.load_model(settings.model_crack)
        elif model_name == "puddle":
            detector = YoloV7Detector(
                conf=settings.detection_conf,
                iou=settings.detection_iou,
                device=settings.inference_device,
                model_tag="puddle",
            )
            detector.load_model(settings.model_puddle)
        elif model_name == "fod":
            detector = YoloV7Detector(
                conf=settings.detection_conf,
                iou=settings.detection_iou,
                device=settings.inference_device,
                model_tag="fod",
            )
            detector.load_model(settings.model_fod)
        elif model_name == "plate":
            detector = PlateDetector(
                conf=settings.plate_detection_conf,
                iou=settings.detection_iou,
                device=settings.inference_device,
            )
            detector.load_model(settings.model_plate)
        self._detectors[model_name] = detector
        return detector


inspection_pipeline = InspectionPipeline()
