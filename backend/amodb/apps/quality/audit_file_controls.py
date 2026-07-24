"""Controlled audit file mutation routes.

The original checklist upload route accepted any audit participant and allowed the
controlled source to be replaced after report issuance or audit closure. This
module replaces that single POST operation with fail-closed authorization,
content-signature validation and safe old-file cleanup.
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import services as audit_services
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user

from .router import (
    AUDIT_CHECKLIST_ALLOWED_EXTENSIONS,
    AUDIT_CHECKLIST_ALLOWED_MIME_TYPES,
    AUDIT_CHECKLIST_DIR,
    MAX_AUDIT_CHECKLIST_BYTES,
    _audit_metadata,
    _current_amo_id,
    _get_audit_for_amo,
    _is_quality_admin,
    _normalized_upload_mime,
    _sanitize_checklist_filename,
    _serialize_audit,
    router,
)
from .schemas import QMSAuditOut


_PDF_MAGIC = b"%PDF-"
_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_ZIP_MAGIC = b"PK\x03\x04"


def _audit_status_value(audit: object) -> str:
    status = getattr(audit, "status", "")
    return str(getattr(status, "value", status) or "").upper()


def _require_checklist_editor(current_user: account_models.User, audit: object) -> None:
    if _is_quality_admin(current_user):
        return
    assigned_ids = {
        str(value)
        for value in (
            getattr(audit, "lead_auditor_user_id", None),
            getattr(audit, "observer_auditor_user_id", None),
            getattr(audit, "assistant_auditor_user_id", None),
        )
        if value
    }
    if str(current_user.id) in assigned_ids:
        return
    raise HTTPException(
        status_code=403,
        detail="Only the assigned audit team or an AMO administrator may replace the controlled checklist.",
    )


def _validate_checklist_signature(path: Path, extension: str) -> None:
    with path.open("rb") as handle:
        prefix = handle.read(8)

    if extension == ".pdf":
        if not prefix.startswith(_PDF_MAGIC):
            raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF document.")
        return

    if extension == ".doc":
        if prefix != _OLE_MAGIC:
            raise HTTPException(status_code=415, detail="The uploaded file is not a valid legacy Word document.")
        return

    if extension == ".docx":
        if not prefix.startswith(_ZIP_MAGIC):
            raise HTTPException(status_code=415, detail="The uploaded file is not a valid Word document package.")
        try:
            with zipfile.ZipFile(path) as package:
                names = set(package.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise HTTPException(status_code=415, detail="The uploaded package is not a valid Word document.")
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=415, detail="The uploaded Word document package is corrupt.") from exc
        return

    raise HTTPException(status_code=415, detail="Checklist extension is not allowed.")


def _approved_existing_checklist_path(value: object) -> Path | None:
    if not value:
        return None
    root = AUDIT_CHECKLIST_DIR.resolve()
    candidate = Path(str(value)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


_extension_router = APIRouter(
    prefix="/quality",
    tags=["Quality / QMS"],
    dependencies=[Depends(require_module("quality"))],
)


@_extension_router.post("/audits/{audit_id}/checklist", response_model=QMSAuditOut)
def upload_controlled_audit_checklist(
    audit_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_checklist_editor(current_user, audit)

    if _audit_status_value(audit) == "CLOSED":
        raise HTTPException(status_code=409, detail="This audit is closed. The checklist is an immutable retained record.")
    if audit.report_file_ref:
        raise HTTPException(status_code=409, detail="The audit report has been issued. The controlled checklist is read-only.")

    original_name = _sanitize_checklist_filename(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in AUDIT_CHECKLIST_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Checklist extension is not allowed. Upload PDF, DOC, or DOCX only.")
    mime_type = _normalized_upload_mime(file)
    if mime_type not in AUDIT_CHECKLIST_ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Checklist MIME type is not allowed. Upload PDF, DOC, or DOCX only.")

    target_dir = AUDIT_CHECKLIST_DIR / str(audit.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid4().hex}_{original_name}"
    previous_path = _approved_existing_checklist_path(audit.checklist_file_ref)
    size_bytes = 0
    digest = hashlib.sha256()

    try:
        with target_path.open("xb") as handle:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > MAX_AUDIT_CHECKLIST_BYTES:
                    raise HTTPException(status_code=413, detail="Checklist exceeds the 15MB limit.")
                digest.update(chunk)
                handle.write(chunk)
        if size_bytes <= 0:
            raise HTTPException(status_code=422, detail="Checklist file is empty.")
        _validate_checklist_signature(target_path, extension)

        audit.checklist_file_ref = str(target_path)
        audit_services.log_event(
            db,
            amo_id=audit.amo_id,
            actor_user_id=current_user.id,
            entity_type="qms_audit",
            entity_id=str(audit.id),
            action="replace_checklist" if previous_path else "upload_checklist",
            before={"checklist_file_name": previous_path.name if previous_path else None},
            after={
                "checklist_file_name": original_name,
                "size_bytes": size_bytes,
                "mime_type": mime_type,
                "sha256": digest.hexdigest(),
            },
            correlation_id=str(uuid4()),
            metadata={**(_audit_metadata(request) or {}), "controlled_source": True},
            critical=True,
        )
        db.commit()
        db.refresh(audit)
    except HTTPException:
        db.rollback()
        target_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        db.rollback()
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Checklist upload could not be saved.") from exc

    if previous_path and previous_path != target_path:
        previous_path.unlink(missing_ok=True)
    return _serialize_audit(audit, db)


_ORIGINAL_PATH = "/quality/audits/{audit_id}/checklist"
router.routes[:] = [
    route
    for route in router.routes
    if not (
        str(getattr(route, "path", "")) == _ORIGINAL_PATH
        and "POST" in (getattr(route, "methods", None) or set())
    )
]
router.routes[0:0] = list(_extension_router.routes)
