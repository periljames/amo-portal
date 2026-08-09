from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from . import models
from .audit_notice_models import QualityAuditNotice, QualityAuditNoticeEvent, QualityAuditNoticePolicy
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


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
    if audit.auditee_user_id or getattr(audit, "auditee_email", None) or audit.auditee:
        recipients.append({
            "role": "AUDITEE",
            "user_id": audit.auditee_user_id,
            "name": audit.auditee,
            "email": getattr(audit, "auditee_email", None),
        })
    for role, user_id in (
        ("LEAD_AUDITOR", audit.lead_auditor_user_id),
        ("OBSERVER_AUDITOR", audit.observer_auditor_user_id),
        ("ASSISTANT_AUDITOR", audit.assistant_auditor_user_id),
    ):
        if user_id:
            recipients.append({"role": role, "user_id": user_id})
    external = getattr(audit, "external_auditees", None)
    if isinstance(external, list):
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
    return f"Audit Notice — {reference} — {audit.title}"


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
    rows = db.query(QualityAuditNotice).options(selectinload(QualityAuditNotice.events)).filter(
        QualityAuditNotice.amo_id == ctx.amo_id,
        QualityAuditNotice.audit_id == audit_id,
    ).order_by(QualityAuditNotice.revision_no.desc()).limit(100).all()
    return {"items": [_notice_dict(row) for row in rows]}


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
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = _create_notice(db=db, ctx=ctx, audit=audit, payload=payload, supersedes=None)
    db.commit()
    return _notice_dict(db.query(QualityAuditNotice).options(selectinload(QualityAuditNotice.events)).filter(QualityAuditNotice.id == row.id).one())


@router.post("/audits/{audit_id}/notices/{notice_id}/revisions", status_code=status.HTTP_201_CREATED)
def revise_audit_notice(
    audit_id: uuid.UUID,
    notice_id: str,
    payload: NoticeRevisionCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
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
    return _notice_dict(db.query(QualityAuditNotice).options(selectinload(QualityAuditNotice.events)).filter(QualityAuditNotice.id == row.id).one())


@router.post("/audits/{audit_id}/notices/{notice_id}/transitions")
def transition_audit_notice(
    audit_id: uuid.UUID,
    notice_id: str,
    payload: NoticeTransition,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = db.query(QualityAuditNotice).options(selectinload(QualityAuditNotice.events)).filter(
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
