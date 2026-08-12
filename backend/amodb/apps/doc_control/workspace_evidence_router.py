from __future__ import annotations

import hashlib
import os
import re
import uuid
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import evidence_models as em
from .workspace_service import (
    audit,
    get_manual,
    get_profile,
    get_revision,
    require_control_user,
    require_manual_access,
    resolve_tenant,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Evidence"])

EVIDENCE_ROOT = Path(os.getenv("DOCUMENT_EVIDENCE_DIR", "uploads/document-control-evidence")).resolve()
MAX_EVIDENCE_BYTES = 25 * 1024 * 1024
ALLOWED_CATEGORIES = {
    "GENERAL",
    "WORKFLOW",
    "AUTHORITY",
    "DISTRIBUTION",
    "CONTROLLED_COPY",
    "REVIEW",
    "EXTERNAL_SOURCE",
    "CHANGE",
}
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx", ".txt", ".csv", ".eml"}
MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".eml": "message/rfc822",
}


def _safe_filename(value: str | None) -> str:
    name = Path(value or "evidence").name
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return safe[:220] or "evidence"


def _validate_file_signature(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail={
                "code": "EVIDENCE_FILE_TYPE_UNSUPPORTED",
                "message": "Evidence must be PDF, PNG, JPEG, DOCX, XLSX, TXT, CSV or EML.",
            },
        )
    if suffix == ".pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="The uploaded PDF evidence has an invalid file signature")
    if suffix == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=422, detail="The uploaded PNG evidence has an invalid file signature")
    if suffix in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=422, detail="The uploaded JPEG evidence has an invalid file signature")
    if suffix in {".docx", ".xlsx"}:
        if not content.startswith(b"PK"):
            raise HTTPException(status_code=422, detail="The uploaded Office evidence has an invalid file signature")
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=422, detail="The uploaded Office evidence is not a valid package") from exc
        required = "word/document.xml" if suffix == ".docx" else "xl/workbook.xml"
        if required not in names:
            raise HTTPException(status_code=422, detail="The uploaded Office evidence does not match its file extension")
    return MIME_BY_EXTENSION[suffix]


def _serialize(tenant_slug: str, row: em.DocumentEvidenceAsset) -> dict:
    return {
        "asset_id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "category": row.category,
        "purpose": row.purpose,
        "filename": row.filename,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "description": row.description,
        "uploaded_by_user_id": row.uploaded_by_user_id,
        "source_context": dict(row.source_context_json or {}),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "download_url": f"/doc-control/workspace/t/{tenant_slug}/documents/{row.manual_id}/evidence-assets/{row.id}/download",
    }


def validate_evidence_references(
    db: Session,
    *,
    tenant_id: str,
    manual_id: str,
    evidence: list[dict] | None,
) -> list[dict]:
    """Validate browser-supplied evidence against immutable DMS assets.

    Browser clients may only submit ``asset_id`` references. System-generated
    evidence such as the effective revision checksum is appended server-side by
    controlled decision routes and therefore does not pass through here.
    """
    items = list(evidence or [])
    if not items:
        return []
    asset_ids: list[str] = []
    for item in items:
        asset_id = str((item or {}).get("asset_id") or "").strip()
        if not asset_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CONTROLLED_EVIDENCE_ASSET_REQUIRED",
                    "message": "Supporting evidence must reference an uploaded Document Control evidence asset.",
                },
            )
        asset_ids.append(asset_id)
    rows = (
        db.query(em.DocumentEvidenceAsset)
        .filter(
            em.DocumentEvidenceAsset.tenant_id == tenant_id,
            em.DocumentEvidenceAsset.manual_id == manual_id,
            em.DocumentEvidenceAsset.id.in_(list(dict.fromkeys(asset_ids))),
        )
        .all()
    )
    by_id = {row.id: row for row in rows}
    missing = [asset_id for asset_id in asset_ids if asset_id not in by_id]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CONTROLLED_EVIDENCE_ASSET_INVALID",
                "message": "One or more evidence assets are missing or outside this governed document.",
                "asset_ids": list(dict.fromkeys(missing)),
            },
        )
    return [
        {
            "asset_id": row.id,
            "filename": row.filename,
            "mime_type": row.mime_type,
            "sha256": row.sha256,
            "size_bytes": row.size_bytes,
            "category": row.category,
        }
        for row in (by_id[asset_id] for asset_id in asset_ids)
    ]


@router.get("/t/{tenant_slug}/documents/{manual_id}/evidence-assets")
def list_document_evidence_assets(
    tenant_slug: str,
    manual_id: str,
    revision_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    query = db.query(em.DocumentEvidenceAsset).filter(
        em.DocumentEvidenceAsset.tenant_id == tenant.amo_id,
        em.DocumentEvidenceAsset.manual_id == manual.id,
    )
    if revision_id:
        get_revision(db, manual, revision_id)
        query = query.filter(em.DocumentEvidenceAsset.revision_id == revision_id)
    rows = query.order_by(em.DocumentEvidenceAsset.created_at.desc(), em.DocumentEvidenceAsset.id.desc()).limit(200).all()
    return {"items": [_serialize(tenant.slug, row) for row in rows], "max_items": 200}


@router.post("/t/{tenant_slug}/documents/{manual_id}/evidence-assets")
async def upload_document_evidence_asset(
    tenant_slug: str,
    manual_id: str,
    request: Request,
    artifact: UploadFile = File(...),
    revision_id: str | None = Form(None),
    category: str = Form("GENERAL"),
    purpose: str | None = Form(None),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    if revision_id:
        get_revision(db, manual, revision_id)
    normalized_category = str(category or "GENERAL").strip().upper()
    if normalized_category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=422, detail="Unsupported Document Control evidence category")
    content = await artifact.read(MAX_EVIDENCE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Evidence file is empty")
    if len(content) > MAX_EVIDENCE_BYTES:
        raise HTTPException(status_code=413, detail="Document Control evidence files are limited to 25 MB")
    filename = _safe_filename(artifact.filename)
    mime_type = _validate_file_signature(filename, content)
    sha256 = hashlib.sha256(content).hexdigest()
    date_token = datetime.utcnow().strftime("%Y%m%d")
    target_dir = EVIDENCE_ROOT / tenant.slug.lower() / manual.id / date_token
    target_dir.mkdir(parents=True, exist_ok=True)
    path = (target_dir / f"{uuid.uuid4().hex}_{filename}").resolve()
    if EVIDENCE_ROOT not in path.parents:
        raise HTTPException(status_code=500, detail="Evidence storage path could not be resolved safely")
    path.write_bytes(content)
    row = em.DocumentEvidenceAsset(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision_id,
        category=normalized_category,
        purpose=(purpose or "").strip()[:128] or None,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=sha256,
        storage_path=str(path),
        description=(description or "").strip() or None,
        uploaded_by_user_id=current_user.id,
        source_context_json={
            "user_agent": request.headers.get("user-agent", "n/a")[:255],
            "original_content_type": artifact.content_type,
        },
    )
    try:
        db.add(row)
        db.flush()
        audit(
            db,
            tenant,
            request,
            "document.evidence.uploaded",
            "document_evidence_asset",
            row.id,
            {
                "manual_id": manual.id,
                "revision_id": revision_id,
                "category": normalized_category,
                "filename": filename,
                "sha256": sha256,
                "size_bytes": len(content),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    db.refresh(row)
    return _serialize(tenant.slug, row)


@router.get("/t/{tenant_slug}/documents/{manual_id}/evidence-assets/{asset_id}/download")
def download_document_evidence_asset(
    tenant_slug: str,
    manual_id: str,
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    row = (
        db.query(em.DocumentEvidenceAsset)
        .filter(
            em.DocumentEvidenceAsset.id == asset_id,
            em.DocumentEvidenceAsset.tenant_id == tenant.amo_id,
            em.DocumentEvidenceAsset.manual_id == manual.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Document Control evidence asset not found")
    path = Path(row.storage_path).resolve()
    if EVIDENCE_ROOT not in path.parents or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="The retained evidence file is unavailable")
    if hashlib.sha256(path.read_bytes()).hexdigest() != row.sha256:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONTROLLED_EVIDENCE_CHECKSUM_MISMATCH",
                "message": "The retained evidence file no longer matches its recorded checksum.",
            },
        )
    return FileResponse(
        path,
        media_type=row.mime_type,
        filename=row.filename,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": row.sha256,
            "X-Document-Evidence-ID": row.id,
        },
    )
