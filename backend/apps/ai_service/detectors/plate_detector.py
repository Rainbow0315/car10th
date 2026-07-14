"""车牌检测 + OCR 识别"""
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any, Dict, List

import cv2
import numpy as np

from .base import BaseDetector


class PlateDetector(BaseDetector):
    def __init__(self, *, conf: float, iou: float, device: str) -> None:
        super().__init__(conf=conf, iou=iou, device=device)
        self.model = None
        self._ocr_available = False

    def load_model(self, weight_path: str) -> None:
        from ultralytics import YOLO
        self.model = YOLO(weight_path)
        # 检测 OCR 是否可用（PaddleOCR 子进程）
        try:
            subprocess.run(
                ["python", "-c", "from paddleocr import PaddleOCR; print('ok')"],
                capture_output=True, timeout=10, encoding="utf-8", errors="replace",
            )
            self._ocr_available = True
            print("[PlateDetector] PaddleOCR available")
        except Exception:
            self._ocr_available = False
            print("[PlateDetector] OCR not available, will return plate boxes only")

    def unload(self) -> None:
        """释放模型内存"""
        self.model = None
        self._ocr_available = False

    def detect(self, image_path: str) -> List[Dict[str, Any]]:
        if self.model is None:
            raise RuntimeError("PlateDetector 尚未加载模型")

        results = self.model(image_path, conf=0.3, verbose=False)
        if not results or results[0].boxes is None:
            return []

        img = cv2.imread(image_path)
        if img is None:
            img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)

        detections = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf = float(box.conf[0])
            h, w = img.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            plate_text = ""
            if self._ocr_available and (y2 > y1 and x2 > x1):
                plate_text = self._run_ocr(img[y1:y2, x1:x2])

            label = plate_text if plate_text else "license_plate"
            detections.append({
                "label": label,
                "confidence": round(conf, 3),
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "extra": {"plate_number": plate_text, "model": "plate"},
            })

        return detections

    def _run_ocr(self, plate_crop: np.ndarray) -> str:
        """通过子进程调用 PaddleOCR"""
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                tmp_path = f.name
                cv2.imwrite(tmp_path, plate_crop)

            proc = subprocess.run(
                [os.sys.executable, "-c", """
import sys, json
try:
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(lang='ch', use_angle_cls=False, show_log=False)
    result = ocr.ocr(sys.argv[1])[0]
    text = ' '.join([line[1][0] for line in result]) if result else ''
except:
    text = ''
print(json.dumps({'combined': text}))
""", tmp_path],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace",
            )
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

            lines = proc.stdout.strip().split("\n")
            json_line = lines[-1] if lines else "{}"
            import json
            return json.loads(json_line).get("combined", "")
        except Exception:
            return ""
