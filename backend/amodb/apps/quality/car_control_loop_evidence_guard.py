from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_write_db

from . import models
from .car_control_loop_models import QualityCARMilestone
from .car_control_loop_router import _enum_value, _load_car
from .car_control_loop_session_context import set_persistent_control_loop_context
from .router import _audit_metadata, _store_car_attachment
from .schemas import CARAttachmentOut
from .tenant_security import TenantContext, assert_quality_permission, write_tenant_context

router = APIRouter(prefix="/cars/{car_id}/control-loop/attachments", tags=["Quality CAR control-loop evidence"])
_TERMINAL_CAR_STATUSES = {"CLOSED", "CANCELLED"}


def _assert_evidence_manage(db: Session, ctx: TenantContext) -> None:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_persistent_control_loop_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def _attachment_out(car_id: UUID, attachment: models.CARAttachment) -> CARAttachmentOut:
    return CARAttachmentOut(
        id=attachment.id,
        car_id=attachment.car_id,
        filename=attachment.filename,
        description=getattr(attachment, "description", None),
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        uploaded_at=attachment.uploaded_at,
        download_url=f"/quality/cars/{car_id}/control-loop/attachments/{attachment.id}/download",
    )


def _require_mutable_car(car: models.CorrectiveActionRequest) -> None:
    state = str(_enum_value(car.status) or "").upper()
    if state in _TERMINAL_CAR_STATUSES:
        raise HTTPException(status_code=409, detail="Evidence cannot be changed after the CAR is closed or cancelled.")


def _clear_attachment_milestone_references(
    db: Session,
    *,
    amo_id: str,
    car_id: UUID,
    attachment_id: UUID,
) -> int:
    prefix = f"car-attachment:{attachment_id}:"
    changed = 0
    milestones = (
        db.query(QualityCARMilestone)
        .filter(
            QualityCARMilestone.amo_id == amo_id,
            QualityCARMilestone.car_id == car_id,
        )
        .with_for_update()
        .all()
    )
    for milestone in milestones:
        raw = str(milestone.evidence_ref or "").strip()
        if not raw:
            continue
        refs = [part.strip() for part in raw.split(";") if part.strip()]
        retained = [part for part in refs if not part.startswith(prefix)]
        if retained == refs:
            continue
        milestone.evidence_ref = "; ".join(retained) or None
        changed += 1
    return changed


@router.get("", response_model=list[CARAttachmentOut])
def list_control_loop_attachments(
    car_id: UUID,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    _assert_evidence_manage(db, ctx)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id)
    rows = (
        db.query(models.CARAttachment)
        .filter(models.CARAttachment.car_id == car.id)
        .order_by(models.CARAttachment.uploaded_at.asc())
        .all()
    )
    return [_attachment_out(car.id, row) for row in rows]


@router.post("", response_model=CARAttachmentOut, status_code=status.HTTP_201_CREATED)
def upload_control_loop_attachment(
    car_id: UUID,
    file: UploadFile = File(...),
    description: Optional[str] = Form(default=None),
    request: Request = None,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    _assert_evidence_manage(db, ctx)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    _require_mutable_car(car)
    target_path, original_name, sha256, size_bytes = _store_car_attachment(car.id, file)
    attachment = models.CARAttachment(
        car_id=car.id,
        filename=original_name,
        description=(description or "").strip()[:500] or None,
        file_ref=str(target_path),
        content_type=file.content_type,
        size_bytes=size_bytes,
        sha256=sha256,
    )
    db.add(attachment)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=car.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="qms_car_attachment",
        entity_id=str(attachment.id),
        action="control_loop_uploaded",
        after={"car_id": str(car.id), "filename": attachment.filename, "sha256": attachment.sha256},
        metadata=_audit_metadata(request) if request else {"module": "quality", "surface": "car-control-loop"},
    )
    db.commit()
    set_persistent_control_loop_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    db.refresh(attachment)
    return _attachment_out(car.id, attachment)


@router.get("/{attachment_id}/download", response_class=FileResponse)
def download_control_loop_attachment(
    car_id: UUID,
    attachment_id: UUID,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    _assert_evidence_manage(db, ctx)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id)
    attachment = (
        db.query(models.CARAttachment)
        .filter(models.CARAttachment.id == attachment_id, models.CARAttachment.car_id == car.id)
        .first()
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    file_path = Path(attachment.file_ref)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file missing on server.")
    return FileResponse(path=file_path, filename=attachment.filename, media_type=attachment.content_type or "application/octet-stream")


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_control_loop_attachment(
    car_id: UUID,
    attachment_id: UUID,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    _assert_evidence_manage(db, ctx)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    _require_mutable_car(car)
    attachment = (
        db.query(models.CARAttachment)
        .filter(models.CARAttachment.id == attachment_id, models.CARAttachment.car_id == car.id)
        .with_for_update()
        .first()
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    cleared_links = _clear_attachment_milestone_references(
        db,
        amo_id=ctx.amo_id,
        car_id=car.id,
        attachment_id=attachment.id,
    )
    file_ref = attachment.file_ref
    db.delete(attachment)
    audit_services.log_event(
        db,
        amo_id=car.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="qms_car_attachment",
        entity_id=str(attachment_id),
        action="control_loop_deleted",
        before={"car_id": str(car.id), "filename": attachment.filename},
        after={"cleared_milestone_references": cleared_links},
        metadata=_audit_metadata(request),
    )
    db.commit()
    try:
        Path(file_ref).unlink(missing_ok=True)
    except Exception:
        pass
    return None
