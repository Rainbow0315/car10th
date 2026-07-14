"""License plate detector with optional PaddleOCR recognition."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List

from apps.ai_service.detectors.base import BaseDetector


class PlateDetector(BaseDetector):
    def __init__(self, *, conf: float, iou: float, device: str) -> None:
        super().__init__(conf=conf, iou=iou, device=device)
        self.model = None
        self._ocr_available = False

    def load_model(self, weight_path: str) -> None:
        from ultralytics import YOLO

        self.model = YOLO(weight_path)
        self._ocr_available = self._check_ocr_available()
        if self._ocr_available:
            print("[PlateDetector] PaddleOCR available", flush=True)
        else:
            print("[PlateDetector] OCR unavailable; returning plate boxes only", flush=True)

    def unload(self) -> None:
        self.model = None
        self._ocr_available = False

    def detect(self, image_path: str) -> List[Dict[str, Any]]:
        if self.model is None:
            raise RuntimeError("PlateDetector model is not loaded")

        results = self.model(image_path, conf=self.conf, iou=self.iou, verbose=False)
        if not results or results[0].boxes is None:
            return []

        import cv2
        import numpy as np

        image = cv2.imread(image_path)
        if image is None:
            image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"cannot read image: {image_path}")

        height, width = image.shape[:2]
        detections: List[Dict[str, Any]] = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            x1 = max(0, min(width, x1))
            x2 = max(0, min(width, x2))
            y1 = max(0, min(height, y1))
            y2 = max(0, min(height, y2))
            confidence = float(box.conf[0])

            plate_number = ""
            if self._ocr_available and y2 > y1 and x2 > x1:
                plate_number = self._run_ocr(image[y1:y2, x1:x2])

            label = plate_number if plate_number else "license_plate"
            detections.append(
                {
                    "label": label,
                    "confidence": round(confidence, 3),
                    "bbox": [float(x1), float(y1), float(x2), float(y2)],
                    "extra": {
                        "plate_number": plate_number,
                        "model": "plate",
                    },
                }
            )

        return detections

    def _check_ocr_available(self) -> bool:
        try:
            proc = subprocess.run(
                [sys.executable, "-c", "from paddleocr import PaddleOCR; print('ok')"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
            )
            return proc.returncode == 0
        except Exception:
            return False

    def _run_ocr(self, plate_crop: Any) -> str:
        import cv2

        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as file:
                tmp_path = file.name
            cv2.imwrite(tmp_path, plate_crop)

            proc = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    """
import json
import sys

try:
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(lang="ch", use_angle_cls=False, show_log=False)
    result = ocr.ocr(sys.argv[1])[0]
    text = "".join(line[1][0] for line in result) if result else ""
except Exception:
    text = ""

print(json.dumps({"plate_number": text}, ensure_ascii=False))
""",
                    tmp_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
            )
            lines = proc.stdout.strip().splitlines()
            payload = json.loads(lines[-1]) if lines else {}
            return str(payload.get("plate_number") or "").strip()
        except Exception:
            return ""
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
