from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from common.config.settings import settings


app = FastAPI(title="Car10th Cloud File Service")


class InspectionFrameUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=180)
    content_base64: str = Field(..., min_length=1)
    content_type: str = "image/jpeg"


class InspectionFrameUploadResponse(BaseModel):
    filename: str
    image_path: str
    image_url: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "cloud_file_service"}


@app.post(
    "/api/cloud-files/inspection-frames",
    response_model=InspectionFrameUploadResponse,
)
def upload_inspection_frame(payload: InspectionFrameUploadRequest):
    filename = _safe_filename(payload.filename)
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="content_base64 is invalid") from exc
    if not content:
        raise HTTPException(status_code=400, detail="empty file content")

    storage = _storage_dir()
    path = storage / filename
    path.write_bytes(content)
    return InspectionFrameUploadResponse(
        filename=filename,
        image_path=str(path),
        image_url=f"{settings.cloud_file_public_base_url.rstrip('/')}/api/cloud-files/inspection-frames/{filename}",
    )


@app.get("/api/cloud-files/inspection-frames/{filename}")
def get_inspection_frame(filename: str):
    path = _storage_dir() / _safe_filename(filename)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"inspection frame not found: {filename}")
    return FileResponse(path, media_type=_media_type(path))


def _storage_dir() -> Path:
    path = Path(settings.cloud_file_storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="filename is invalid")
    return name


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    return "application/octet-stream"
