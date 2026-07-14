from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
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
