"""License plate detector with optional PaddleOCR recognition."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Tuple
from urllib import error, request

from apps.ai_service.detectors.base import BaseDetector
from common.config.settings import settings


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
            ocr_attempted = False
            ocr_backend = "none"
            ocr_detail = ""
            ocr_debug_image_url = ""
            cloud_ocr_candidates: List[Dict[str, Any]] = []
            if y2 > y1 and x2 > x1:
                plate_crop = self._prepare_plate_crop(image, (x1, y1, x2, y2))
            else:
                plate_crop = None
            if self._ocr_available and plate_crop is not None:
                ocr_attempted = True
                ocr_backend = "paddleocr"
                plate_number = self._run_ocr(plate_crop)
            elif plate_crop is not None:
                cloud_result = self._run_cloud_ocr(plate_crop)
                ocr_attempted = bool(cloud_result.get("attempted"))
                if ocr_attempted:
                    ocr_backend = "cloud"
                    print(
                        "[PlateDetector] Cloud OCR result "
                        + json.dumps(
                            {
                                "plate_number": cloud_result.get("plate_number") or "",
                                "candidates": cloud_result.get("candidates") or [],
                                "debug_image_url": cloud_result.get("debug_image_url") or "",
                                "detail": cloud_result.get("detail") or "",
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                plate_number = str(cloud_result.get("plate_number") or "")
                ocr_detail = str(cloud_result.get("detail") or "")
                ocr_debug_image_url = str(cloud_result.get("debug_image_url") or "")
                cloud_ocr_candidates = list(cloud_result.get("candidates") or [])

            label = plate_number if plate_number else "license_plate"
            detections.append(
                {
                    "label": label,
                    "confidence": round(confidence, 3),
                    "bbox": [float(x1), float(y1), float(x2), float(y2)],
                    "extra": {
                        "plate_number": plate_number,
                        "ocr_available": self._ocr_available or ocr_backend == "cloud",
                        "ocr_attempted": ocr_attempted,
                        "ocr_backend": ocr_backend,
                        "ocr_detail": ocr_detail,
                        "ocr_debug_image_url": ocr_debug_image_url,
                        "ocr_candidates": cloud_ocr_candidates,
                        "model": "plate",
                    },
                }
            )

        return detections

    def _prepare_plate_crop(self, image: Any, bbox: Tuple[int, int, int, int]) -> Any:
        import cv2

        height, width = image.shape[:2]
        x1, y1, x2, y2 = bbox
        box_w = max(1, x2 - x1)
        box_h = max(1, y2 - y1)
        pad_x = max(4, int(box_w * 0.18))
        pad_y = max(4, int(box_h * 0.28))
        x1 = max(0, x1 - pad_x)
        x2 = min(width, x2 + pad_x)
        y1 = max(0, y1 - pad_y)
        y2 = min(height, y2 + pad_y)

        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return crop

        crop_h, crop_w = crop.shape[:2]
        target_w = 640
        if crop_w < target_w:
            scale = target_w / max(1, crop_w)
            crop = cv2.resize(
                crop,
                (target_w, max(1, int(crop_h * scale))),
                interpolation=cv2.INTER_CUBIC,
            )

        return crop

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
                    r"""
import json
import re
import sys

try:
    from paddleocr import PaddleOCR

    try:
        ocr = PaddleOCR(lang="ch", use_angle_cls=False, show_log=False)
    except TypeError:
        ocr = PaddleOCR(lang="ch", use_angle_cls=False)

    raw = ocr.ocr(sys.argv[1])

    def walk(value):
        texts = []
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            for key in ("text", "rec_text", "plate_number", "label"):
                item = value.get(key)
                if isinstance(item, str):
                    texts.append(item)
            for item in value.values():
                texts.extend(walk(item))
        elif isinstance(value, (list, tuple)):
            if len(value) >= 2 and isinstance(value[1], (list, tuple)) and value[1]:
                maybe_text = value[1][0]
                if isinstance(maybe_text, str):
                    texts.append(maybe_text)
            for item in value:
                texts.extend(walk(item))
        return texts

    candidates = []
    for item in walk(raw):
        clean = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", item).upper()
        if len(clean) >= 4:
            candidates.append(clean)
    text = max(candidates, key=len) if candidates else ""
except Exception as exc:
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

    def _run_cloud_ocr(self, plate_crop: Any) -> Dict[str, Any]:
        if not settings.plate_ocr_service_enabled or not settings.plate_ocr_service_url:
            return {"attempted": False, "plate_number": "", "candidates": []}

        import cv2

        ok, encoded = cv2.imencode(".jpg", plate_crop)
        if not ok:
            return {
                "attempted": True,
                "plate_number": "",
                "candidates": [],
                "detail": "cannot encode plate crop",
            }

        payload = json.dumps(
            {
                "filename": "plate_crop.jpg",
                "content_base64": base64.b64encode(encoded.tobytes()).decode("ascii"),
                "content_type": "image/jpeg",
            }
        ).encode("utf-8")
        req = request.Request(
            settings.plate_ocr_service_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=settings.plate_ocr_service_timeout_sec) as resp:
                body = resp.read().decode("utf-8")
        except (OSError, error.URLError) as exc:
            return {
                "attempted": True,
                "plate_number": "",
                "candidates": [],
                "detail": f"cloud OCR unreachable: {exc}",
            }

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            return {
                "attempted": True,
                "plate_number": "",
                "candidates": [],
                "detail": f"cloud OCR returned invalid JSON: {exc}",
            }
        return {
            "attempted": True,
            "plate_number": str(data.get("plate_number") or "").strip(),
            "candidates": data.get("candidates") or [],
            "debug_image_url": str(data.get("debug_image_url") or ""),
            "detail": str(data.get("detail") or ""),
        }
