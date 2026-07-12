from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from apps.ai_service.detectors import CrackDetector, YoloV7Detector
from common.config.settings import settings
from common.schemas.inspection import DetectorResult, ImageInspectionRequest, ImageInspectionResponse, InspectionSummary


class InspectionPipeline:
    def __init__(self) -> None:
        self._detectors: Dict[str, object] = {}

    def inspect_image(self, request: ImageInspectionRequest) -> ImageInspectionResponse:
        image_path = Path(request.image_path).expanduser()
        if not image_path.is_absolute():
            image_path = (Path.cwd() / image_path).resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"图片不存在: {image_path}")

        enabled_models = self._normalize_models(request.enabled_models)
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
            robot_code=request.robot_code,
            camera_code=request.camera_code,
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

    def _normalize_models(self, models: Iterable[str]) -> List[str]:
        normalized = []
        for model_name in models:
            value = str(model_name).strip().lower()
            if value and value not in normalized:
                normalized.append(value)
        return normalized or list(settings.default_enabled_models)

    def _get_detector(self, model_name: str):
        if model_name in self._detectors:
            return self._detectors[model_name]

        if model_name == "crack":
            detector = CrackDetector(conf=settings.detection_conf, iou=settings.detection_iou, device=settings.inference_device)
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
        else:
            raise RuntimeError(f"不支持的模型: {model_name}")

        self._detectors[model_name] = detector
        return detector


inspection_pipeline = InspectionPipeline()
