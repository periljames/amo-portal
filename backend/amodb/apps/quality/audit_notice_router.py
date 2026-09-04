from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session, selectinload

from amodb import storage
from amodb.apps.accounts import models as account_models
from amodb.apps.notifications import models as notification_models
from amodb.apps.notifications import service as notification_service
from amodb.database import get_read_db, get_write_db

from . import models
from .audit_notice_document import render_audit_notice_pdf
from .audit_notice_models import QualityAuditNotice, QualityAuditNoticeArtifact, QualityAuditNoticeEvent, QualityAuditNoticePolicy
from .audit_occurrence_completion_models import QualityAuditMeeting
from .tenant_security import TenantContext, assert_quality_permission, assert_quality_permission_any, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit notice governance"])

NoticeAction = Literal["SUBMIT", "RETURN", "APPROVE", "GENERATE", "DELIVER", "ACKNOWLEDGE", "CANCEL"]
ExceptionType = Literal["EMERGENCY", "UNANNOUNCED"]


class NoticePolicyCreate(BaseModel):
    policy_code: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=3, max_length=255)
    audit_kind: str | None = Field(default=None, max_length=32)
    minimum_notice_days: int = Field(default=14, ge=0, le=365)
    review_required: bool = True
    acknowledgement_required: bool = True
    emergency_exception_allowed: bool = True
    unannounced_exception_allowed: bool = True


class NoticePolicyPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    audit_kind: str | None = Field(default=None, max_length=32)
    minimum_notice_days: int | None = Field(default=None, ge=0, le=365)
    review_required: bool | None = None
    acknowledgement_required: bool | None = None
    emergency_exception_allowed: bool | None = None
    unannounced_exception_allowed: bool | None = None
    is_active: bool | None = None


class NoticeDraftCreate(BaseModel):
    policy_id: str | None = Field(default=None, max_length=36)
    notice_date: date = Field(default_factory=date.today)
    exception_type: ExceptionType | None = None
    exception_reason: str | None = Field(default=None, max_length=4000)
    subject: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=20000)
    reason: str = Field(min_length=8, max_length=4000)

    @model_validator(mode="after")
    def validate_exception(self) -> "NoticeDraftCreate":
        if self.exception_type and len((self.exception_reason or "").strip()) < 8:
            raise ValueError("An emergency or unannounced notice exception requires a reason of at least 8 characters.")
        return self


class NoticeRevisionCreate(NoticeDraftCreate):
    pass


class NoticeTransition(BaseModel):
    action: NoticeAction
    reason: str = Field(min_length=8, max_length=4000)
    delivery_channel: str | None = Field(default=None, max_length=32)
    delivery_reference: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_delivery(self) -> "NoticeTransition":
        if self.action == "DELIVER":
            if len((self.delivery_channel or "").strip()) < 2:
                raise ValueError("Delivery channel is required when recording notice delivery.")
            if len((self.delivery_reference or "").strip()) < 3:
                raise ValueError("Delivery reference is required when recording notice delivery.")
        return self


class NoticeSubmit(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)


_NOTICE_PERMISSION = "qms.audit.notice.manage"
_MAX_NOTICE_PDF_BYTES = int(os.getenv("QMS_AUDIT_NOTICE_MAX_PDF_BYTES", str(15 * 1024 * 1024)) or "0")
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")
_FORM_NUMBER = os.getenv("QMS_AUDIT_NOTICE_FORM_NUMBER", "QAM/45").strip() or "QAM/45"
_FORM_ISSUE_DATE = os.getenv("QMS_AUDIT_NOTICE_FORM_ISSUE_DATE", "24 Sep 20").strip() or "24 Sep 20"
_FORM_REVISION = os.getenv("QMS_AUDIT_NOTICE_FORM_REVISION", "02").strip() or "02"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return row


def _policy_dict(row: QualityAuditNoticePolicy) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "policy_code": row.policy_code,
        "title": row.title,
        "audit_kind": row.audit_kind,
        "minimum_notice_days": row.minimum_notice_days,
        "review_required": row.review_required,
        "acknowledgement_required": row.acknowledgement_required,
        "emergency_exception_allowed": row.emergency_exception_allowed,
        "unannounced_exception_allowed": row.unannounced_exception_allowed,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _event_dict(row: QualityAuditNoticeEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "reason": row.reason,
        "before_snapshot": row.before_snapshot,
        "after_snapshot": row.after_snapshot,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at,
    }


def _artifact_dict(row: QualityAuditNoticeArtifact | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "source_type": row.source_type,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": int(row.size_bytes or 0),
        "sha256": row.sha256,
        "signed_by_user_id": row.signed_by_user_id,
        "signed_by_name": row.signed_by_name,
        "signed_by_title": row.signed_by_title,
        "signed_at": row.signed_at,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
    }


def _notice_dict(row: QualityAuditNotice) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_id": str(row.audit_id),
        "policy_id": row.policy_id,
        "revision_no": row.revision_no,
        "status": row.status,
        "required_notice_days": row.required_notice_days,
        "notice_date": row.notice_date,
        "exception_type": row.exception_type,
        "exception_reason": row.exception_reason,
        "subject": row.subject,
        "body": row.body,
        "audit_snapshot": row.audit_snapshot or {},
        "recipient_snapshot": row.recipient_snapshot or [],
        "delivery_channel": row.delivery_channel,
        "delivery_reference": row.delivery_reference,
        "supersedes_notice_id": row.supersedes_notice_id,
        "approved_by_user_id": row.approved_by_user_id,
        "approved_at": row.approved_at,
        "generated_by_user_id": row.generated_by_user_id,
        "generated_at": row.generated_at,
        "delivered_by_user_id": row.delivered_by_user_id,
        "delivered_at": row.delivered_at,
        "acknowledged_by_user_id": row.acknowledged_by_user_id,
        "acknowledged_at": row.acknowledged_at,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "artifact": _artifact_dict(row.artifact),
        "events": [_event_dict(item) for item in list(row.events or [])],
    }


def _snapshot(row: QualityAuditNotice) -> dict[str, Any]:
    return {
        "status": row.status,
        "revision_no": row.revision_no,
        "notice_date": row.notice_date.isoformat() if row.notice_date else None,
        "exception_type": row.exception_type,
        "delivery_channel": row.delivery_channel,
        "delivery_reference": row.delivery_reference,
    }


def _audit_snapshot(audit: models.QMSAudit) -> dict[str, Any]:
    return {
        "audit_id": str(audit.id),
        "audit_ref": audit.audit_ref,
        "title": audit.title,
        "kind": _enum_value(audit.kind),
        "domain": _enum_value(audit.domain),
        "scope": audit.scope,
        "criteria": audit.criteria,
        "planned_start": audit.planned_start.isoformat() if audit.planned_start else None,
        "planned_end": audit.planned_end.isoformat() if audit.planned_end else None,
        "auditee": audit.auditee,
        "auditee_user_id": audit.auditee_user_id,
        "lead_auditor_user_id": audit.lead_auditor_user_id,
        "observer_auditor_user_id": audit.observer_auditor_user_id,
        "assistant_auditor_user_id": audit.assistant_auditor_user_id,
    }


def _recipient_snapshot(audit: models.QMSAudit) -> list[dict[str, Any]]:
    recipients: list[dict[str, Any]] = []
    if bool(audit.notify_auditees) and (audit.auditee_user_id or getattr(audit, "auditee_email", None) or audit.auditee):
        recipients.append({
            "role": "AUDITEE",
            "user_id": audit.auditee_user_id,
            "name": audit.auditee,
            "email": getattr(audit, "auditee_email", None),
        })
    if bool(audit.notify_auditors):
        for role, user_id in (
            ("LEAD_AUDITOR", audit.lead_auditor_user_id),
            ("OBSERVER_AUDITOR", audit.observer_auditor_user_id),
            ("ASSISTANT_AUDITOR", audit.assistant_auditor_user_id),
        ):
            if user_id:
                recipients.append({"role": role, "user_id": user_id})
    external = getattr(audit, "external_auditees", None)
    if bool(audit.notify_auditees) and isinstance(external, list):
        for item in external:
            if isinstance(item, dict):
                recipients.append({"role": "EXTERNAL_AUDITEE", **item})
    return recipients


def _effective_policy(
    db: Session,
    *,
    amo_id: str,
    audit: models.QMSAudit,
    policy_id: str | None = None,
) -> QualityAuditNoticePolicy | None:
    query = db.query(QualityAuditNoticePolicy).filter(
        QualityAuditNoticePolicy.amo_id == amo_id,
        QualityAuditNoticePolicy.is_active.is_(True),
    )
    if policy_id:
        row = query.filter(QualityAuditNoticePolicy.id == policy_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Active audit notice policy not found.")
        return row
    kind = _enum_value(audit.kind)
    rows = query.filter(
        (QualityAuditNoticePolicy.audit_kind == kind) | (QualityAuditNoticePolicy.audit_kind.is_(None))
    ).order_by(QualityAuditNoticePolicy.audit_kind.desc(), QualityAuditNoticePolicy.updated_at.desc()).limit(10).all()
    return rows[0] if rows else None


def _policy_values(policy: QualityAuditNoticePolicy | None) -> dict[str, Any]:
    return {
        "minimum_notice_days": policy.minimum_notice_days if policy else 14,
        "review_required": bool(policy.review_required) if policy else True,
        "acknowledgement_required": bool(policy.acknowledgement_required) if policy else True,
        "emergency_exception_allowed": bool(policy.emergency_exception_allowed) if policy else True,
        "unannounced_exception_allowed": bool(policy.unannounced_exception_allowed) if policy else True,
    }


def _validate_notice_period(audit: models.QMSAudit, notice: QualityAuditNotice, policy: QualityAuditNoticePolicy | None) -> None:
    settings = _policy_values(policy)
    if notice.exception_type:
        allowed = settings["emergency_exception_allowed"] if notice.exception_type == "EMERGENCY" else settings["unannounced_exception_allowed"]
        if not allowed:
            raise HTTPException(status_code=409, detail=f"The active notice policy does not permit {notice.exception_type.lower()} exceptions.")
        if len((notice.exception_reason or "").strip()) < 8:
            raise HTTPException(status_code=409, detail="A governed notice exception requires an attributable reason.")
        if audit.planned_start and notice.notice_date > audit.planned_start:
            raise HTTPException(status_code=409, detail="Notice date cannot be after the planned audit start date.")
        return
    if audit.planned_start is None:
        raise HTTPException(status_code=409, detail="Audit planned start date is required before a notice can be approved.")
    latest_permitted = audit.planned_start - timedelta(days=notice.required_notice_days)
    if notice.notice_date > latest_permitted:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Configured audit notice period is insufficient.",
                "required_notice_days": notice.required_notice_days,
                "notice_date": notice.notice_date.isoformat(),
                "planned_start": audit.planned_start.isoformat(),
                "latest_permitted_notice_date": latest_permitted.isoformat(),
                "required_action": "Move the audit, issue the notice earlier, or record an authorized emergency/unannounced exception.",
            },
        )


def _default_subject(audit: models.QMSAudit) -> str:
    reference = audit.audit_ref or "Audit"
    return f"Audit Notice - {reference} - {audit.title}"


def _default_body(audit: models.QMSAudit, notice_date: date) -> str:
    scope = audit.scope or "As defined in the approved audit scope."
    criteria = audit.criteria or "Applicable approved requirements and procedures."
    planned = audit.planned_start.isoformat() if audit.planned_start else "To be confirmed"
    return (
        f"This is controlled notice of {audit.audit_ref or 'the scheduled audit'}: {audit.title}.\n\n"
        f"Planned start: {planned}\n"
        f"Scope: {scope}\n"
        f"Criteria: {criteria}\n"
        f"Notice date: {notice_date.isoformat()}\n\n"
        "Please ensure requested records, responsible personnel and relevant facilities are available for the audit."
    )


def _notice_query(db: Session):
    return db.query(QualityAuditNotice).options(
        selectinload(QualityAuditNotice.events),
        selectinload(QualityAuditNotice.artifact),
    )


def _actor(db: Session, *, ctx: TenantContext) -> account_models.User:
    user = db.query(account_models.User).filter(
        account_models.User.id == ctx.user_id,
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
    ).first()
    if user is None or bool(getattr(user, "is_system_account", False)):
        raise HTTPException(status_code=403, detail="An active human Quality user is required to issue an audit notice.")
    return user


def _display_name(user: account_models.User | None, fallback: str = "") -> str:
    if user is None:
        return fallback
    return str(user.full_name or f"{user.first_name} {user.last_name}" or fallback).strip() or fallback


def _timezone_for_amo(amo: account_models.AMO) -> ZoneInfo:
    try:
        return ZoneInfo(str(amo.time_zone or "UTC"))
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _ordinal(day: int) -> str:
    if 10 < day % 100 < 14:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _date_label(value: date | None) -> str:
    if value is None:
        return "date to be confirmed"
    return f"{value.strftime('%A')} {_ordinal(value.day)} {value.strftime('%B %Y')}"


def _time_label(value: datetime) -> str:
    hour = value.hour % 12 or 12
    minute = f":{value.minute:02d}" if value.minute else ":00"
    return f"{hour}{minute} {'am' if value.hour < 12 else 'pm'}"


def _meeting_payload(row: QualityAuditMeeting | None, *, zone: ZoneInfo) -> dict[str, Any] | None:
    if row is None:
        return None
    start = row.scheduled_start
    end = row.scheduled_end
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    start = start.astimezone(zone)
    if end is not None:
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        end = end.astimezone(zone)
    window = f"{_date_label(start.date())} from {_time_label(start)}"
    if end is not None:
        window += f" to {_time_label(end)}" if end.date() == start.date() else f" to {_date_label(end.date())} {_time_label(end)}"
    return {
        "window": window,
        "location": row.location,
        "conference_url": row.conference_url,
        "start": start,
        "end": end,
    }


def _meetings(db: Session, *, amo_id: str, audit_id: uuid.UUID, zone: ZoneInfo) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    rows = db.query(QualityAuditMeeting).filter(
        QualityAuditMeeting.amo_id == amo_id,
        QualityAuditMeeting.audit_id == audit_id,
        QualityAuditMeeting.meeting_type.in_(("OPENING", "CLOSING")),
    ).order_by(QualityAuditMeeting.scheduled_start.asc()).all()
    opening = next((row for row in rows if row.meeting_type == "OPENING"), None)
    closing = next((row for row in reversed(rows) if row.meeting_type == "CLOSING"), None)
    return _meeting_payload(opening, zone=zone), _meeting_payload(closing, zone=zone)


def _resolved_recipients(
    db: Session,
    *,
    amo_id: str,
    snapshot: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved: list[dict[str, Any]] = []
    deliverable: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in snapshot:
        item = dict(raw) if isinstance(raw, dict) else {}
        user_id = str(item.get("user_id") or "").strip() or None
        user = None
        if user_id:
            user = db.query(account_models.User).filter(
                account_models.User.id == user_id,
                account_models.User.amo_id == amo_id,
                account_models.User.is_active.is_(True),
            ).first()
        name = str(item.get("name") or "").strip() or _display_name(user)
        email = str(item.get("email") or "").strip() or str(getattr(user, "email", "") or "").strip()
        current = {**item, "user_id": user_id, "name": name or None, "email": email or None}
        resolved.append(current)
        marker = email.lower()
        if email and marker not in seen:
            seen.add(marker)
            deliverable.append(current)
    return resolved, deliverable


def _formal_staff(snapshot: list[dict[str, Any]], audit: models.QMSAudit) -> list[str]:
    names = [
        str(item.get("name") or item.get("designation") or "").strip()
        for item in snapshot
        if str(item.get("role") or "").upper() in {"AUDITEE", "EXTERNAL_AUDITEE"}
    ]
    names = [name for name in names if name]
    if not names and audit.auditee:
        names.append(str(audit.auditee))
    return names


def _logo_path(db: Session, *, amo_id: str) -> Path | None:
    asset = db.query(account_models.AMOAsset).filter(
        account_models.AMOAsset.amo_id == amo_id,
        account_models.AMOAsset.kind == account_models.AMOAssetKind.CRS_LOGO,
        account_models.AMOAsset.is_active.is_(True),
    ).order_by(account_models.AMOAsset.created_at.desc()).first()
    if asset is None or not asset.storage_path:
        return None
    try:
        path = storage.materialize(asset.storage_path, expected_sha256=asset.sha256)
    except (FileNotFoundError, OSError, ValueError):
        return None
    return path if path.suffix.lower() in {".png", ".jpg", ".jpeg"} else None


def _render_notice(
    db: Session,
    *,
    ctx: TenantContext,
    audit: models.QMSAudit,
    notice: QualityAuditNotice,
    issuer: account_models.User,
    signed_at: datetime,
    is_preview: bool,
) -> bytes:
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == ctx.amo_id).one()
    zone = _timezone_for_amo(amo)
    opening, closing = _meetings(db, amo_id=ctx.amo_id, audit_id=audit.id, zone=zone)
    resolved, _ = _resolved_recipients(db, amo_id=ctx.amo_id, snapshot=_recipient_snapshot(audit))
    audit_dates = _date_label(audit.planned_start)
    if audit.planned_end and audit.planned_end != audit.planned_start:
        audit_dates += f" to {_date_label(audit.planned_end)}"
    opening_end = opening.get("end") if opening else None
    closing_start = closing.get("start") if closing else None
    if isinstance(opening_end, datetime) and isinstance(closing_start, datetime):
        sequence_window = f"{_time_label(opening_end)} to {_time_label(closing_start)}"
    else:
        sequence_window = audit_dates
    local_signed = signed_at.astimezone(zone)
    return render_audit_notice_pdf(
        amo_name=amo.name,
        contact_email=amo.contact_email,
        notice_id=str(notice.id),
        revision_no=notice.revision_no,
        notice_date_display=_date_label(notice.notice_date),
        audit_ref=audit.audit_ref,
        audit_title=audit.title,
        audit_date_display=audit_dates,
        auditee=audit.auditee,
        subject=notice.subject,
        opening_meeting=opening,
        closing_meeting=closing,
        sequence_window=sequence_window,
        staff=_formal_staff(resolved, audit),
        issuer_name=_display_name(issuer, "Quality Department"),
        issuer_title=str(issuer.position_title or getattr(issuer.role, "value", issuer.role) or "Quality Officer").replace("_", " ").title(),
        signed_at_display=f"{_date_label(local_signed.date())}, {_time_label(local_signed)} {zone.key}",
        form_number=_FORM_NUMBER,
        form_issue_date=_FORM_ISSUE_DATE,
        form_revision=_FORM_REVISION,
        logo_path=_logo_path(db, amo_id=ctx.amo_id),
        is_preview=is_preview,
    )


def _safe_pdf_filename(audit: models.QMSAudit, notice: QualityAuditNotice, *, preview: bool = False) -> str:
    reference = _SAFE_FILENAME.sub("_", str(audit.audit_ref or audit.id)).strip(" ._") or "audit"
    marker = "_PREVIEW" if preview else ""
    return f"{reference}_Audit_Notice_R{notice.revision_no}{marker}.pdf"


def _artifact_path(row: QualityAuditNoticeArtifact) -> Path:
    try:
        return storage.materialize(row.storage_ref, expected_sha256=row.sha256)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="The controlled audit notice PDF is unavailable.") from exc


def _store_generated_artifact(
    db: Session,
    *,
    ctx: TenantContext,
    audit: models.QMSAudit,
    notice: QualityAuditNotice,
    issuer: account_models.User,
    signed_at: datetime,
) -> QualityAuditNoticeArtifact:
    payload = _render_notice(db, ctx=ctx, audit=audit, notice=notice, issuer=issuer, signed_at=signed_at, is_preview=False)
    filename = _safe_pdf_filename(audit, notice)
    stored = storage.put_stream(
        BytesIO(payload),
        key=f"quality/audit-notices/{ctx.amo_id}/{audit.id}/{notice.id}/{uuid.uuid4().hex}_{filename}",
        content_type="application/pdf",
    )
    artifact = QualityAuditNoticeArtifact(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        notice_id=str(notice.id),
        source_type="GENERATED",
        storage_ref=stored.uri,
        filename=filename,
        content_type="application/pdf",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        signed_by_user_id=ctx.user_id,
        signed_by_name=_display_name(issuer),
        signed_by_title=str(issuer.position_title or getattr(issuer.role, "value", issuer.role) or "Quality Officer").replace("_", " ").title(),
        signed_at=signed_at,
        created_by_user_id=ctx.user_id,
    )
    try:
        db.add(artifact)
        db.flush()
    except Exception:
        try:
            storage.delete(stored.uri)
        except Exception:
            pass
        raise
    notice.artifact = artifact
    return artifact


def _notice_email_correlation(notice_id: str, recipient_email: str) -> str:
    recipient_digest = hashlib.sha256(recipient_email.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"audit-notice:{notice_id}:{recipient_digest}"


def _notice_notification(
    db: Session,
    *,
    ctx: TenantContext,
    audit: models.QMSAudit,
    notice: QualityAuditNotice,
    recipient: dict[str, Any],
) -> None:
    user_id = str(recipient.get("user_id") or "").strip()
    if not user_id:
        return
    existing = db.query(models.QMSNotification.id).filter(
        models.QMSNotification.amo_id == ctx.amo_id,
        models.QMSNotification.user_id == user_id,
        models.QMSNotification.entity_type == "AUDIT_NOTICE",
        models.QMSNotification.entity_id == str(notice.id),
    ).first()
    if existing:
        return
    db.add(models.QMSNotification(
        amo_id=ctx.amo_id,
        user_id=user_id,
        message=f"Audit notice issued: {audit.audit_ref} - {audit.title}.",
        severity=models.QMSNotificationSeverity.ACTION_REQUIRED,
        created_by_user_id=ctx.user_id,
        action_url=f"/maintenance/{ctx.amo_code}/quality/audits/{audit.audit_ref}/setup#notice",
        action_label="Open audit notice",
        entity_type="AUDIT_NOTICE",
        entity_id=str(notice.id),
    ))


def _add_event(
    db: Session,
    *,
    ctx: TenantContext,
    notice: QualityAuditNotice,
    event_type: str,
    reason: str,
    before: dict[str, Any] | None = None,
) -> None:
    db.add(QualityAuditNoticeEvent(
        amo_id=ctx.amo_id,
        audit_id=notice.audit_id,
        notice_id=notice.id,
        event_type=event_type,
        reason=reason.strip(),
        before_snapshot=before,
        after_snapshot=_snapshot(notice),
        actor_user_id=ctx.user_id,
    ))


@router.get("/audit-notice-policies")
def list_notice_policies(
    active_only: bool = Query(default=False),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityAuditNoticePolicy).filter(QualityAuditNoticePolicy.amo_id == ctx.amo_id)
    if active_only:
        query = query.filter(QualityAuditNoticePolicy.is_active.is_(True))
    rows = query.order_by(QualityAuditNoticePolicy.audit_kind.asc(), QualityAuditNoticePolicy.policy_code.asc()).limit(100).all()
    return {"items": [_policy_dict(row) for row in rows]}


@router.post("/audit-notice-policies", status_code=status.HTTP_201_CREATED)
def create_notice_policy(
    payload: NoticePolicyCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = QualityAuditNoticePolicy(
        amo_id=ctx.amo_id,
        policy_code=payload.policy_code.strip().upper(),
        title=payload.title.strip(),
        audit_kind=payload.audit_kind.strip().upper() if payload.audit_kind else None,
        minimum_notice_days=payload.minimum_notice_days,
        review_required=payload.review_required,
        acknowledgement_required=payload.acknowledgement_required,
        emergency_exception_allowed=payload.emergency_exception_allowed,
        unannounced_exception_allowed=payload.unannounced_exception_allowed,
        is_active=True,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _policy_dict(row)


@router.patch("/audit-notice-policies/{policy_id}")
def patch_notice_policy(
    policy_id: str,
    payload: NoticePolicyPatch,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditNoticePolicy).filter(
        QualityAuditNoticePolicy.amo_id == ctx.amo_id,
        QualityAuditNoticePolicy.id == policy_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit notice policy not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "audit_kind" and isinstance(value, str):
            value = value.strip().upper() or None
        setattr(row, field, value)
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return _policy_dict(row)


@router.get("/audits/{audit_id}/notices")
def list_audit_notices(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    rows = _notice_query(db).filter(
        QualityAuditNotice.amo_id == ctx.amo_id,
        QualityAuditNotice.audit_id == audit_id,
    ).order_by(QualityAuditNotice.revision_no.desc()).limit(100).all()
    return {"items": [_notice_dict(row) for row in rows]}


async def _stage_uploaded_pdf(file: UploadFile) -> tuple[Path, str, int, str]:
    filename = Path(str(file.filename or "audit-notice.pdf")).name.strip() or "audit-notice.pdf"
    filename = _SAFE_FILENAME.sub("_", filename).strip(" .")[:255] or "audit-notice.pdf"
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=422, detail="The audit notice attachment must be a PDF file.")
    if file.content_type and file.content_type.lower() not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=422, detail="The audit notice attachment must use the application/pdf content type.")

    root = storage.cache_root()
    root.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix="audit-notice-", suffix=".pdf", dir=str(root))
    os.close(descriptor)
    path = Path(raw_path)
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if _MAX_NOTICE_PDF_BYTES and total > _MAX_NOTICE_PDF_BYTES:
                    raise HTTPException(status_code=413, detail="The audit notice PDF exceeds the configured upload limit.")
                digest.update(chunk)
                output.write(chunk)
        if total <= 0:
            raise HTTPException(status_code=422, detail="The uploaded audit notice PDF is empty.")
        with path.open("rb") as source:
            signature = source.read(5)
        if signature != b"%PDF-":
            raise HTTPException(status_code=422, detail="The uploaded file is not a valid PDF document.")
        try:
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(str(path))
            page_count = len(document)
            document.close()
            if page_count <= 0:
                raise ValueError("PDF has no pages")
        except Exception as exc:
            raise HTTPException(status_code=422, detail="The uploaded PDF could not be opened safely.") from exc
        return path, filename, total, digest.hexdigest()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.post("/audits/{audit_id}/notices/{notice_id}/attachment")
async def upload_audit_notice_attachment(
    audit_id: uuid.UUID,
    notice_id: str,
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission_any(db, ctx, "qms.audit.manage", _NOTICE_PERMISSION)
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = _notice_query(db).filter(
        QualityAuditNotice.amo_id == ctx.amo_id,
        QualityAuditNotice.audit_id == audit_id,
        QualityAuditNotice.id == notice_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit notice not found.")
    if row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="A notice PDF may only be attached while the notice is in draft.")

    staged, filename, size_bytes, sha256 = await _stage_uploaded_pdf(file)
    stored = None
    old_ref = row.artifact.storage_ref if row.artifact is not None else None
    try:
        stored = storage.put_file(
            staged,
            key=f"quality/audit-notices/{ctx.amo_id}/{audit.id}/{row.id}/{uuid.uuid4().hex}_{filename}",
            content_type="application/pdf",
        )
        artifact = row.artifact
        if artifact is None:
            artifact = QualityAuditNoticeArtifact(
                amo_id=ctx.amo_id,
                audit_id=audit.id,
                notice_id=str(row.id),
                source_type="UPLOADED",
                storage_ref=stored.uri,
                filename=filename,
                content_type="application/pdf",
                size_bytes=size_bytes,
                sha256=sha256,
                created_by_user_id=ctx.user_id,
            )
            db.add(artifact)
            row.artifact = artifact
        else:
            artifact.source_type = "UPLOADED"
            artifact.storage_ref = stored.uri
            artifact.filename = filename
            artifact.content_type = "application/pdf"
            artifact.size_bytes = size_bytes
            artifact.sha256 = sha256
            artifact.signed_by_user_id = None
            artifact.signed_by_name = None
            artifact.signed_by_title = None
            artifact.signed_at = None
            artifact.created_by_user_id = ctx.user_id
            artifact.created_at = _utcnow()
        db.commit()
    except Exception:
        db.rollback()
        if stored is not None:
            try:
                storage.delete(stored.uri)
            except Exception:
                pass
        raise
    finally:
        staged.unlink(missing_ok=True)

    if old_ref and stored is not None and old_ref != stored.uri:
        try:
            storage.delete(old_ref)
        except Exception:
            pass
    refreshed = _notice_query(db).filter(QualityAuditNotice.id == row.id).one()
    return _notice_dict(refreshed)


@router.get("/audits/{audit_id}/notices/{notice_id}/preview")
def preview_audit_notice_pdf(
    audit_id: uuid.UUID,
    notice_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = _notice_query(db).filter(
        QualityAuditNotice.amo_id == ctx.amo_id,
        QualityAuditNotice.audit_id == audit_id,
        QualityAuditNotice.id == notice_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit notice not found.")
    if row.artifact is not None:
        path = _artifact_path(row.artifact)
        return FileResponse(
            path,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{row.artifact.filename}"',
                "Cache-Control": "private, no-store",
                "X-Content-SHA256": row.artifact.sha256,
            },
        )
    issuer = db.query(account_models.User).filter(
        account_models.User.id == row.created_by_user_id,
        account_models.User.amo_id == ctx.amo_id,
    ).first() or _actor(db, ctx=ctx)
    payload = _render_notice(db, ctx=ctx, audit=audit, notice=row, issuer=issuer, signed_at=_utcnow(), is_preview=True)
    filename = _safe_pdf_filename(audit, row, preview=True)
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/audits/{audit_id}/notices/{notice_id}/document")
def download_audit_notice_document(
    audit_id: uuid.UUID,
    notice_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = _notice_query(db).filter(
        QualityAuditNotice.amo_id == ctx.amo_id,
        QualityAuditNotice.audit_id == audit_id,
        QualityAuditNotice.id == notice_id,
    ).first()
    if row is None or row.artifact is None:
        raise HTTPException(status_code=404, detail="The controlled audit notice PDF has not been generated or attached.")
    path = _artifact_path(row.artifact)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=row.artifact.filename,
        headers={"Cache-Control": "private, no-store", "X-Content-SHA256": row.artifact.sha256},
    )


@router.post("/audits/{audit_id}/notices/{notice_id}/submit")
def submit_and_deliver_audit_notice(
    audit_id: uuid.UUID,
    notice_id: str,
    payload: NoticeSubmit,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission_any(db, ctx, "qms.audit.manage", _NOTICE_PERMISSION)
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    issuer = _actor(db, ctx=ctx)
    row = _notice_query(db).filter(
        QualityAuditNotice.amo_id == ctx.amo_id,
        QualityAuditNotice.audit_id == audit_id,
        QualityAuditNotice.id == notice_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit notice not found.")
    if row.status in {"DELIVERED", "ACKNOWLEDGED"}:
        return {"notice": _notice_dict(row), "delivery_complete": True, "dispatch": {"attempted": 0, "sent": 0, "failed": 0, "items": []}}
    if row.status not in {"DRAFT", "UNDER_REVIEW", "APPROVED", "GENERATED"}:
        raise HTTPException(status_code=409, detail="This notice revision cannot be submitted.")

    policy = _effective_policy(db, amo_id=ctx.amo_id, audit=audit, policy_id=row.policy_id) if row.policy_id else None
    _validate_notice_period(audit, row, policy)
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == ctx.amo_id).one()
    zone = _timezone_for_amo(amo)
    opening, closing = _meetings(db, amo_id=ctx.amo_id, audit_id=audit.id, zone=zone)
    if opening is None or closing is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "AUDIT_NOTICE_MEETINGS_REQUIRED",
                "message": "Save both the pre-audit briefing and closing meeting before submitting the notice.",
            },
        )

    resolved_snapshot, recipients = _resolved_recipients(
        db,
        amo_id=ctx.amo_id,
        snapshot=_recipient_snapshot(audit),
    )
    auditee_recipients = [
        item for item in recipients
        if str(item.get("role") or "").upper() in {"AUDITEE", "EXTERNAL_AUDITEE"}
    ]
    if not auditee_recipients:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "AUDIT_NOTICE_AUDITEE_EMAIL_REQUIRED",
                "message": "Add an auditee email address and enable auditee notifications before submitting the notice.",
            },
        )

    row.audit_snapshot = _audit_snapshot(audit)
    row.recipient_snapshot = resolved_snapshot
    reason = payload.reason.strip()
    issued_at = _utcnow()
    if row.status == "DRAFT":
        _add_event(db, ctx=ctx, notice=row, event_type="SUBMITTED", reason=reason, before=_snapshot(row))
    if row.status in {"DRAFT", "UNDER_REVIEW"}:
        before = _snapshot(row)
        row.status = "APPROVED"
        row.approved_by_user_id = ctx.user_id
        row.approved_at = issued_at
        _add_event(db, ctx=ctx, notice=row, event_type="APPROVED", reason=reason, before=before)
    if row.status == "APPROVED":
        before = _snapshot(row)
        if row.artifact is None:
            _store_generated_artifact(db, ctx=ctx, audit=audit, notice=row, issuer=issuer, signed_at=issued_at)
        else:
            row.artifact.signed_by_user_id = ctx.user_id
            row.artifact.signed_by_name = _display_name(issuer)
            row.artifact.signed_by_title = str(issuer.position_title or getattr(issuer.role, "value", issuer.role) or "Quality Officer").replace("_", " ").title()
            row.artifact.signed_at = issued_at
        row.status = "GENERATED"
        row.generated_by_user_id = ctx.user_id
        row.generated_at = issued_at
        _add_event(db, ctx=ctx, notice=row, event_type="GENERATED", reason=reason, before=before)

    if row.artifact is None:
        _store_generated_artifact(db, ctx=ctx, audit=audit, notice=row, issuer=issuer, signed_at=issued_at)
    document_path = _artifact_path(row.artifact)
    document_bytes = document_path.read_bytes()
    email_attachment = [{
        "filename": row.artifact.filename,
        "content": document_bytes,
        "content_type": "application/pdf",
    }]
    dispatch_items: list[dict[str, Any]] = []
    for recipient in recipients:
        recipient_email = str(recipient.get("email") or "").strip()
        recipient_user_id = str(recipient.get("user_id") or "").strip() or None
        log = notification_service.send_email(
            template_key="qms_audit_notice_memo",
            recipient=recipient_email,
            subject=row.subject[:255],
            context={
                "recipient_name": recipient.get("name") or recipient_email,
                "recipient_role": recipient.get("role") or "AUDIT_RECIPIENT",
                "audit_ref": audit.audit_ref,
                "audit_title": audit.title,
                "planned_start": audit.planned_start.isoformat() if audit.planned_start else "",
                "planned_end": audit.planned_end.isoformat() if audit.planned_end else "",
                "notice_revision": row.revision_no,
                "notice_document": row.artifact.filename,
                "action_url": f"/maintenance/{ctx.amo_code}/quality/audits/{audit.audit_ref}/setup#notice",
            },
            correlation_id=_notice_email_correlation(str(row.id), recipient_email),
            email_class="CRITICAL",
            recipient_user_id=recipient_user_id,
            amo_id=ctx.amo_id,
            db=db,
            audit_context={
                "purpose": "audit-notice",
                "audit_id": str(audit.id),
                "notice_id": str(row.id),
                "recipient_role": recipient.get("role"),
            },
            attachments=email_attachment,
        )
        delivery_status = str(getattr(log.status, "value", log.status))
        dispatch_items.append({
            "email": recipient_email,
            "role": recipient.get("role"),
            "status": delivery_status,
            "message_id": log.provider_message_id,
            "error": log.error,
        })

    sent = sum(1 for item in dispatch_items if item["status"] == notification_models.EmailStatus.SENT.value)
    delivery_complete = bool(dispatch_items) and sent == len(dispatch_items)
    before_delivery = _snapshot(row)
    row.delivery_channel = "EMAIL"
    row.delivery_reference = f"Email attachment delivery {sent}/{len(dispatch_items)}"
    if delivery_complete:
        row.status = "DELIVERED"
        row.delivered_by_user_id = ctx.user_id
        row.delivered_at = issued_at
        audit.upcoming_notice_sent_at = issued_at
        _add_event(db, ctx=ctx, notice=row, event_type="DELIVERED", reason=reason, before=before_delivery)
        for recipient in resolved_snapshot:
            _notice_notification(db, ctx=ctx, audit=audit, notice=row, recipient=recipient)
    db.commit()
    refreshed = _notice_query(db).filter(QualityAuditNotice.id == row.id).one()
    return {
        "notice": _notice_dict(refreshed),
        "delivery_complete": delivery_complete,
        "dispatch": {
            "attempted": len(dispatch_items),
            "sent": sent,
            "failed": len(dispatch_items) - sent,
            "items": dispatch_items,
        },
    }


def _create_notice(
    *,
    db: Session,
    ctx: TenantContext,
    audit: models.QMSAudit,
    payload: NoticeDraftCreate,
    supersedes: QualityAuditNotice | None,
) -> QualityAuditNotice:
    policy = _effective_policy(db, amo_id=ctx.amo_id, audit=audit, policy_id=payload.policy_id)
    settings = _policy_values(policy)
    latest = db.query(QualityAuditNotice).filter(
        QualityAuditNotice.amo_id == ctx.amo_id,
        QualityAuditNotice.audit_id == audit.id,
    ).order_by(QualityAuditNotice.revision_no.desc()).with_for_update().first()
    if latest is not None and latest.status == "DRAFT":
        raise HTTPException(status_code=409, detail="A draft audit notice already exists for this audit. Submit, cancel or complete it before creating another revision.")
    row = QualityAuditNotice(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        policy_id=str(policy.id) if policy else None,
        revision_no=(latest.revision_no + 1) if latest else 1,
        status="DRAFT",
        required_notice_days=int(settings["minimum_notice_days"]),
        notice_date=payload.notice_date,
        exception_type=payload.exception_type,
        exception_reason=(payload.exception_reason or "").strip() or None,
        subject=(payload.subject or _default_subject(audit)).strip(),
        body=(payload.body or _default_body(audit, payload.notice_date)).strip(),
        audit_snapshot=_audit_snapshot(audit),
        recipient_snapshot=_recipient_snapshot(audit),
        supersedes_notice_id=str(supersedes.id) if supersedes else None,
        created_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    _add_event(db, ctx=ctx, notice=row, event_type="REVISED" if supersedes else "CREATED", reason=payload.reason)
    return row


@router.post("/audits/{audit_id}/notices", status_code=status.HTTP_201_CREATED)
def create_audit_notice(
    audit_id: uuid.UUID,
    payload: NoticeDraftCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission_any(db, ctx, "qms.audit.manage", _NOTICE_PERMISSION)
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = _create_notice(db=db, ctx=ctx, audit=audit, payload=payload, supersedes=None)
    db.commit()
    return _notice_dict(_notice_query(db).filter(QualityAuditNotice.id == row.id).one())


@router.post("/audits/{audit_id}/notices/{notice_id}/revisions", status_code=status.HTTP_201_CREATED)
def revise_audit_notice(
    audit_id: uuid.UUID,
    notice_id: str,
    payload: NoticeRevisionCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission_any(db, ctx, "qms.audit.manage", _NOTICE_PERMISSION)
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    prior = db.query(QualityAuditNotice).filter(
        QualityAuditNotice.amo_id == ctx.amo_id,
        QualityAuditNotice.audit_id == audit_id,
        QualityAuditNotice.id == notice_id,
    ).first()
    if prior is None:
        raise HTTPException(status_code=404, detail="Audit notice not found.")
    if prior.status == "DRAFT":
        raise HTTPException(status_code=409, detail="A DRAFT notice must be completed or cancelled rather than revised into another draft.")
    row = _create_notice(db=db, ctx=ctx, audit=audit, payload=payload, supersedes=prior)
    db.commit()
    return _notice_dict(_notice_query(db).filter(QualityAuditNotice.id == row.id).one())


@router.post("/audits/{audit_id}/notices/{notice_id}/transitions")
def transition_audit_notice(
    audit_id: uuid.UUID,
    notice_id: str,
    payload: NoticeTransition,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission_any(db, ctx, "qms.audit.manage", _NOTICE_PERMISSION)
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = _notice_query(db).filter(
        QualityAuditNotice.amo_id == ctx.amo_id,
        QualityAuditNotice.audit_id == audit_id,
        QualityAuditNotice.id == notice_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit notice not found.")
    policy = _effective_policy(db, amo_id=ctx.amo_id, audit=audit, policy_id=row.policy_id) if row.policy_id else None
    settings = _policy_values(policy)
    before = _snapshot(row)
    action = payload.action

    if action == "SUBMIT":
        if row.status != "DRAFT":
            raise HTTPException(status_code=409, detail="Only a DRAFT notice may be submitted for review.")
        row.status = "UNDER_REVIEW"
        event_type = "SUBMITTED"
    elif action == "RETURN":
        if row.status != "UNDER_REVIEW":
            raise HTTPException(status_code=409, detail="Only a notice under review may be returned to draft.")
        row.status = "DRAFT"
        event_type = "RETURNED"
    elif action == "APPROVE":
        allowed_states = {"UNDER_REVIEW"} if settings["review_required"] else {"DRAFT", "UNDER_REVIEW"}
        if row.status not in allowed_states:
            raise HTTPException(status_code=409, detail="Notice is not in a state that may be approved under the active policy.")
        _validate_notice_period(audit, row, policy)
        row.status = "APPROVED"
        row.approved_by_user_id = ctx.user_id
        row.approved_at = _utcnow()
        event_type = "APPROVED"
    elif action == "GENERATE":
        if row.status != "APPROVED":
            raise HTTPException(status_code=409, detail="Only an APPROVED notice may be generated.")
        _validate_notice_period(audit, row, policy)
        row.status = "GENERATED"
        row.generated_by_user_id = ctx.user_id
        row.generated_at = _utcnow()
        event_type = "GENERATED"
    elif action == "DELIVER":
        if row.status != "GENERATED":
            raise HTTPException(status_code=409, detail="Only a GENERATED notice may be recorded as delivered.")
        row.status = "DELIVERED"
        row.delivery_channel = (payload.delivery_channel or "").strip().upper()
        row.delivery_reference = (payload.delivery_reference or "").strip()
        row.delivered_by_user_id = ctx.user_id
        row.delivered_at = _utcnow()
        event_type = "DELIVERED"
    elif action == "ACKNOWLEDGE":
        if row.status != "DELIVERED":
            raise HTTPException(status_code=409, detail="Only a DELIVERED notice may be acknowledged.")
        row.status = "ACKNOWLEDGED"
        row.acknowledged_by_user_id = ctx.user_id
        row.acknowledged_at = _utcnow()
        event_type = "ACKNOWLEDGED"
    elif action == "CANCEL":
        if row.status not in {"DRAFT", "UNDER_REVIEW", "APPROVED", "GENERATED"}:
            raise HTTPException(status_code=409, detail="Delivered or acknowledged notices cannot be cancelled; create a controlled revision instead.")
        row.status = "CANCELLED"
        event_type = "CANCELLED"
    else:
        raise HTTPException(status_code=422, detail="Unsupported notice transition.")

    _add_event(db, ctx=ctx, notice=row, event_type=event_type, reason=payload.reason, before=before)
    db.commit()
    db.refresh(row)
    response = _notice_dict(row)
    response["policy"] = {
        **settings,
        "policy_id": str(policy.id) if policy else None,
        "policy_code": policy.policy_code if policy else "SYSTEM_DEFAULT_14_DAY",
    }
    return response
