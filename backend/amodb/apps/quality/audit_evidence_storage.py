from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile


MAX_EVIDENCE_BYTES = int(os.getenv("QMS_AUDIT_EVIDENCE_MAX_BYTES", str(50 * 1024 * 1024)))
_STORAGE_ROOT = Path(os.getenv("QMS_AUDIT_EVIDENCE_DIR", "uploads/qms-audit-evidence")).resolve()
_ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".csv", ".doc", ".docx", ".xls", ".xlsx", ".mp4", ".mov", ".m4a", ".wav"
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")
_CFBF_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass(frozen=True)
class StoredAuditEvidence:
    filename: str
    content_type: str | None
    size_bytes: int
    sha256: str
    storage_ref: str


def safe_filename(value: str | None) -> str:
    raw = Path((value or "evidence").replace("\\", "/")).name
    clean = _SAFE_NAME.sub("_", raw).strip(" .")[:180]
    return clean or "evidence"


def _validate_signature(filename: str, sample: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported evidence type: {suffix or 'unknown'}")
    if suffix == ".pdf" and not sample.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="Uploaded PDF has an invalid signature.")
    if suffix == ".png" and not sample.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=415, detail="Uploaded PNG has an invalid signature.")
    if suffix in {".jpg", ".jpeg"} and not sample.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=415, detail="Uploaded JPEG has an invalid signature.")
    if suffix == ".webp" and not (len(sample) >= 12 and sample[:4] == b"RIFF" and sample[8:12] == b"WEBP"):
        raise HTTPException(status_code=415, detail="Uploaded WEBP has an invalid signature.")
    if suffix in {".docx", ".xlsx"} and not sample.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=415, detail="Uploaded Office evidence has an invalid signature.")
    if suffix in {".doc", ".xls"} and not sample.startswith(_CFBF_MAGIC):
        raise HTTPException(status_code=415, detail="Uploaded legacy Office evidence has an invalid signature.")
    if suffix == ".mp4" and not (len(sample) >= 12 and sample[4:8] == b"ftyp"):
        raise HTTPException(status_code=415, detail="Uploaded MP4 evidence has an invalid signature.")
    if suffix == ".wav" and not (len(sample) >= 12 and sample[:4] == b"RIFF" and sample[8:12] == b"WAVE"):
        raise HTTPException(status_code=415, detail="Uploaded WAV evidence has an invalid signature.")


def storage_root() -> Path:
    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return _STORAGE_ROOT


async def store_audit_evidence(upload: UploadFile, *, amo_id: str, audit_id: str, checklist_item_id: str | None = None) -> StoredAuditEvidence:
    filename = safe_filename(upload.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported evidence type: {suffix or 'unknown'}")
    sample = await upload.read(16)
    _validate_signature(filename, sample)
    await upload.seek(0)

    scope = checklist_item_id or "audit"
    relative = Path(str(amo_id)) / str(audit_id) / str(scope) / f"{uuid.uuid4().hex}_{filename}"
    root = storage_root()
    destination = (root / relative).resolve()
    if root != destination and root not in destination.parents:
        raise HTTPException(status_code=400, detail="Invalid evidence storage target.")
    destination.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    total = 0
    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_EVIDENCE_BYTES:
                    raise HTTPException(status_code=413, detail="Evidence exceeds the configured upload limit.")
                digest.update(chunk)
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return StoredAuditEvidence(
        filename=filename,
        content_type=upload.content_type,
        size_bytes=total,
        sha256=digest.hexdigest(),
        storage_ref=relative.as_posix(),
    )


def resolve_audit_evidence(storage_ref: str) -> Path:
    root = storage_root()
    target = (root / str(storage_ref)).resolve()
    if root != target and root not in target.parents:
        raise HTTPException(status_code=404, detail="Evidence artifact not found.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Evidence artifact not found.")
    return target
