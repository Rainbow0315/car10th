from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import re
import tempfile
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse


BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = Path(
    os.environ.get(
        "CLOUD_FILE_STORAGE_DIR",
        str(BASE_DIR / "runtime" / "inspection" / "cloud_frames"),
    )
)
PUBLIC_BASE_URL = os.environ.get(
    "CLOUD_FILE_PUBLIC_BASE_URL",
    "http://192.168.137.20:8010",
).rstrip("/")
_OCR_ENGINE: Any = None
_OCR_ENGINE_ERROR = ""


class CloudFileHandler(BaseHTTPRequestHandler):
    server_version = "Car10thCloudFile/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok", "service": "cloud_file_server"})
            return
        prefix = "/api/cloud-files/inspection-frames/"
        if path.startswith(prefix):
            self._serve_frame(unquote(path[len(prefix) :]))
            return
        self._json(HTTPStatus.NOT_FOUND, {"detail": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/ocr/plate":
            self._recognize_plate()
            return
        if path != "/api/cloud-files/inspection-frames":
            self._json(HTTPStatus.NOT_FOUND, {"detail": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            filename = _safe_filename(str(payload.get("filename") or ""))
            content = base64.b64decode(str(payload.get("content_base64") or ""), validate=True)
        except (ValueError, json.JSONDecodeError, binascii.Error) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"detail": f"bad upload payload: {exc}"})
            return
        if not content:
            self._json(HTTPStatus.BAD_REQUEST, {"detail": "empty file content"})
            return

        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        target = STORAGE_DIR / filename
        target.write_bytes(content)
        self._json(
            HTTPStatus.OK,
            {
                "filename": filename,
                "image_path": str(target),
                "image_url": f"{PUBLIC_BASE_URL}/api/cloud-files/inspection-frames/{filename}",
            },
        )

    def _recognize_plate(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            content = base64.b64decode(str(payload.get("content_base64") or ""), validate=True)
        except (ValueError, json.JSONDecodeError, binascii.Error) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"detail": f"bad OCR payload: {exc}"})
            return
        if not content:
            self._json(HTTPStatus.BAD_REQUEST, {"detail": "empty image content"})
            return

        try:
            engine = _get_ocr_engine()
        except RuntimeError as exc:
            self._json(
                HTTPStatus.OK,
                {
                    "ocr_available": False,
                    "plate_number": "",
                    "candidates": [],
                    "detail": str(exc),
                },
            )
            return

        suffix = Path(str(payload.get("filename") or "plate.jpg")).suffix or ".jpg"
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as file:
                temp_path = file.name
                file.write(content)
            debug_filename = _save_ocr_debug_image(content, suffix)
            candidates, attempts = _run_ocr_variants(engine, temp_path)
            self._json(
                HTTPStatus.OK,
                {
                    "ocr_available": True,
                    "plate_number": candidates[0]["text"] if candidates else "",
                    "candidates": candidates,
                    "attempts": attempts,
                    "debug_image_url": (
                        f"{PUBLIC_BASE_URL}/api/cloud-files/inspection-frames/{debug_filename}"
                        if debug_filename
                        else ""
                    ),
                },
            )
        except Exception as exc:
            self._json(
                HTTPStatus.OK,
                {
                    "ocr_available": False,
                    "plate_number": "",
                    "candidates": [],
                    "detail": f"OCR failed: {exc}",
                },
            )
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.client_address[0]} - {format % args}")

    def _serve_frame(self, filename: str) -> None:
        try:
            safe = _safe_filename(filename)
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"detail": str(exc)})
            return
        path = STORAGE_DIR / safe
        if not path.exists() or not path.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"detail": f"inspection frame not found: {safe}"})
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: HTTPStatus, body: dict[str, object]) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if not name or name in {".", ".."}:
        raise ValueError("filename is invalid")
    return name


def _get_ocr_engine() -> Any:
    global _OCR_ENGINE, _OCR_ENGINE_ERROR
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    if _OCR_ENGINE_ERROR:
        raise RuntimeError(_OCR_ENGINE_ERROR)
    try:
        from rapidocr_onnxruntime import RapidOCR

        _OCR_ENGINE = RapidOCR()
        return _OCR_ENGINE
    except Exception as exc:
        _OCR_ENGINE_ERROR = f"rapidocr_onnxruntime unavailable: {exc}"
        raise RuntimeError(_OCR_ENGINE_ERROR) from exc


def _save_ocr_debug_image(content: bytes, suffix: str) -> str:
    safe_suffix = suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", suffix or "") else ".jpg"
    filename = f"plate_ocr_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{safe_suffix}"
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    (STORAGE_DIR / filename).write_bytes(content)
    return filename


def _run_ocr_variants(engine: Any, image_path: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    variants = _build_ocr_variants(image_path)
    attempts: list[dict[str, object]] = []
    all_candidates: list[dict[str, object]] = []
    for name, path in variants:
        try:
            raw_result, elapsed = engine(path)
            candidates = _plate_candidates(raw_result)
            attempts.append(
                {
                    "variant": name,
                    "candidate_count": len(candidates),
                    "elapsed": elapsed,
                }
            )
            all_candidates.extend(candidates)
        except Exception as exc:
            attempts.append({"variant": name, "candidate_count": 0, "detail": str(exc)})
        finally:
            if path != image_path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
    return _unique_ocr_candidates(all_candidates), attempts


def _build_ocr_variants(image_path: str) -> list[tuple[str, str]]:
    variants = [("original", image_path)]
    try:
        import cv2
        import numpy as np
    except Exception:
        return variants

    image = cv2.imread(image_path)
    if image is None:
        return variants

    def write_variant(name: str, data: Any) -> None:
        fd, path = tempfile.mkstemp(suffix=f"_{name}.jpg")
        os.close(fd)
        cv2.imwrite(path, data)
        variants.append((name, path))

    height, width = image.shape[:2]
    if width < 900:
        scale = 900 / max(1, width)
        enlarged = cv2.resize(
            image,
            (900, max(1, int(height * scale))),
            interpolation=cv2.INTER_CUBIC,
        )
        write_variant("enlarged", enlarged)
    else:
        enlarged = image

    blurred = cv2.GaussianBlur(enlarged, (0, 0), 1.0)
    sharpened = cv2.addWeighted(enlarged, 1.7, blurred, -0.7, 0)
    write_variant("sharpened", sharpened)

    gray = cv2.cvtColor(sharpened, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    write_variant("contrast", cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR))

    threshold = cv2.adaptiveThreshold(
        clahe,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        9,
    )
    write_variant("threshold", cv2.cvtColor(threshold, cv2.COLOR_GRAY2BGR))
    return variants


def _plate_candidates(raw_result: Any) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for text, score in _walk_ocr_result(raw_result):
        clean = _normalize_plate_text(text)
        if len(clean) < 4:
            continue
        values.append({"text": clean, "score": round(float(score), 4)})
    values.sort(key=lambda item: (len(str(item["text"])), float(item["score"])), reverse=True)

    return _unique_ocr_candidates(values)


def _unique_ocr_candidates(values: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    unique: list[dict[str, object]] = []
    for item in values:
        text = str(item["text"])
        if text in seen:
            continue
        seen.add(text)
        unique.append(item)
    return unique


def _walk_ocr_result(value: Any) -> Iterable[tuple[str, float]]:
    if isinstance(value, str):
        yield value, 0.0
        return
    if isinstance(value, dict):
        text = value.get("text") or value.get("rec_text") or value.get("plate_number")
        score = value.get("score") or value.get("confidence") or value.get("rec_score") or 0.0
        if isinstance(text, str):
            yield text, _safe_float(score)
        for item in value.values():
            yield from _walk_ocr_result(item)
        return
    if isinstance(value, (list, tuple)):
        if len(value) >= 3 and isinstance(value[1], str):
            yield value[1], _safe_float(value[2])
        elif len(value) >= 2 and isinstance(value[1], (list, tuple)) and value[1]:
            text = value[1][0]
            score = value[1][1] if len(value[1]) > 1 else 0.0
            if isinstance(text, str):
                yield text, _safe_float(score)
        for item in value:
            yield from _walk_ocr_result(item)


def _normalize_plate_text(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", value or "").upper()


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    host = os.environ.get("CLOUD_FILE_HOST", "0.0.0.0")
    port = int(os.environ.get("CLOUD_FILE_PORT", "8010"))
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), CloudFileHandler)
    print(f"cloud file server listening on http://{host}:{port}")
    print(f"storage: {STORAGE_DIR}")
    print(f"public base url: {PUBLIC_BASE_URL}")
    server.serve_forever()


if __name__ == "__main__":
    main()
