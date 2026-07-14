from __future__ import annotations

from typing import Any, Dict, List

from .base import BaseDetector


class CrackDetector(BaseDetector):
    def __init__(self, *, conf: float, iou: float, device: str) -> None:
        super().__init__(conf=conf, iou=iou, device=device)
        self.model = None

    def load_model(self, weight_path: str) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("缺少 ultralytics，请先安装依赖后再加载裂缝检测模型") from exc

        self.model = YOLO(weight_path)

    def unload(self) -> None:
        """释放模型内存（分时加载用）"""
        self.model = None

    def detect(self, image_path: str) -> List[Dict[str, Any]]:
        if self.model is None:
            raise RuntimeError("CrackDetector 尚未加载模型")

        results = self.model(image_path, conf=self.conf, iou=self.iou, device=self.device, verbose=False)
        detections: List[Dict[str, Any]] = []
        for result in results:
            for box in result.boxes:
                cls_index = int(box.cls[0]) if box.cls is not None else 0
                label = result.names.get(cls_index, "道面裂缝") if hasattr(result, "names") else "道面裂缝"
                detections.append(
                    {
                        "label": label,
                        "confidence": float(box.conf[0]),
                        "bbox": [float(v) for v in box.xyxy[0].tolist()],
                        "extra": {"class_id": cls_index, "model": "crack"},
                    }
                )
        return detections
