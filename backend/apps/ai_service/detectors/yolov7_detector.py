from __future__ import annotations

from typing import Any, Dict, List

from .base import BaseDetector


class YoloV7Detector(BaseDetector):
    def __init__(self, *, conf: float, iou: float, device: str, model_tag: str) -> None:
        super().__init__(conf=conf, iou=iou, device=device)
        self.model_tag = model_tag
        self.model = None
        self.names: List[str] = []
        self.stride = 32
        self.torch = None
        self.cv2 = None
        self.letterbox = None
        self.non_max_suppression = None
        self.scale_boxes = None

    def load_model(self, weight_path: str) -> None:
        try:
            import cv2
            import torch
        except ImportError as exc:
            raise RuntimeError("缺少 torch / opencv-python-headless，无法加载 YOLOv7 模型") from exc

        try:
            from apps.ai_service.libs.inference_utils import letterbox, non_max_suppression, scale_boxes
            from apps.ai_service.libs.yolov7_standalone import load_yolov7_model
        except ImportError as exc:
            raise RuntimeError(
                "缺少 yolov7_standalone.py 或 inference_utils.py，请先把训练同学提供的 2 个配套文件放到 apps/ai_service/libs/"
            ) from exc

        runtime_device = self.device
        if runtime_device.startswith("cuda") and not torch.cuda.is_available():
            runtime_device = "cpu"
        self.device = runtime_device
        self.model, self.names, self.stride = load_yolov7_model(weight_path, device=runtime_device)
        self.torch = torch
        self.cv2 = cv2
        self.letterbox = letterbox
        self.non_max_suppression = non_max_suppression
        self.scale_boxes = scale_boxes

    def detect(self, image_path: str) -> List[Dict[str, Any]]:
        if self.model is None or self.torch is None or self.cv2 is None:
            raise RuntimeError(f"{self.model_tag} 检测器尚未加载模型")

        image = self.cv2.imread(image_path)
        if image is None:
            raise RuntimeError(f"无法读取图片: {image_path}")

        letterboxed, ratio, pad = self.letterbox(image, 640, stride=self.stride, auto=True)
        tensor = self.torch.from_numpy(letterboxed[:, :, ::-1].transpose(2, 0, 1).copy()).float() / 255.0
        tensor = tensor.unsqueeze(0).to(self.device)

        with self.torch.no_grad():
            pred = self.model(tensor)[0]

        det = self.non_max_suppression(pred, self.conf, self.iou)[0]
        detections: List[Dict[str, Any]] = []
        if det is None or len(det) == 0:
            return detections

        det[:, :4] = self.scale_boxes(tensor.shape[2:], det[:, :4], image.shape, ratio_pad=(ratio, pad))
        det = det.detach().cpu()
        for item in det:
            cls_index = int(item[5])
            label = self.names[cls_index] if cls_index < len(self.names) else f"class_{cls_index}"
            extra: Dict[str, Any] = {"class_id": cls_index, "model": self.model_tag}
            if "·" in label:
                extra["severity"] = label.split("·")[-1]
            detections.append(
                {
                    "label": label,
                    "confidence": float(item[4]),
                    "bbox": [float(v) for v in item[:4].tolist()],
                    "extra": extra,
                }
            )
        return detections
