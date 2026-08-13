from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.apps.realtime import messaging as realtime_messaging
from amodb.apps.realtime import models as realtime_models
from amodb.apps.realtime import schemas as realtime_schemas
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import retention_models as rm
from .workspace_decision_policy import is_decision_approver, require_decision_approver
from .workspace_retention_router import _due_status, _payload, _row
from .workspace_service import audit, get_manual, require_control_user, resolve_tenant, utcnow


router = APIRouter(prefix="/workspace", tags=["Document Control Retention Accountability"])


class RetentionRequestWithApprover(BaseModel):
    approver_user_id: str
    justification: str = Field(min_length=3, max_length=8000)


class RetentionDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    justification: str = Field(min_length=3, max_length=8000)


def _retention_payload(row: rm.DocumentRetentionDisposition) -> dict:
    return {**_payload(row), "approver_user_id": row.approver_user_id}


def _notification_action_url(tenant_slug: str, row: rm.DocumentRetentionDisposition) -> str:
    return (
        f"/maintenance/{tenant_slug}/document-control/library/{row.manual_id}"
        f"?tab=overview&retention={row.id}"
    )


def _queue_notification(
    db: Session,
    *,
    tenant,
    user_id: str | None,
    row: rm.DocumentRetentionDisposition,
    event: str,
    title: str,
    body: str,
) -> None:
    if not user_id:
        return
    user = (
        db.query(account_models.User)
        .filter(
            account_models.User.id == user_id,
            account_models.User.amo_id == tenant.amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .first()
    )
    if not user:
        return
    dedupe_key = f"doc-control-retention:{row.id}:{event}:{user.id}"[:255]
    existing = (
        db.query(realtime_models.PortalNotification.id)
        .filter(
            realtime_models.PortalNotification.amo_id == tenant.amo_id,
            realtime_models.PortalNotification.user_id == user.id,
            realtime_models.PortalNotification.dedupe_key == dedupe_key,
        )
        .first()
    )
    if existing:
        return
    notification = realtime_models.PortalNotification(
        amo_id=tenant.amo_id,
        user_id=user.id,
        kind="DOCUMENT_CONTROL_RETENTION",
        title=title[:255],
        body=body[:1000],
        entity_type="document_retention_disposition",
        entity_id=row.id,
        action_url=_notification_action_url(tenant.slug, row),
        dedupe_key=dedupe_key,
        metadata_json={
            "event": event,
            "manual_id": row.manual_id,
            "retention_id": row.id,
            "source_type": row.source_type,
            "source_label": row.source_label,
            "status": row.status,
        },
    )
    db.add(notification)
    db.flush()
    realtime_messaging._queue_user_event(
        db,
        amo_id=tenant.amo_id,
        user_id=str(user.id),
        kind=realtime_schemas.RealtimeKind.NOTIFICATION_CREATED,
        payload=realtime_messaging.notification_payload(notification),
    )


def _assigned_approver(db: Session, *, tenant, approver_user_id: str, requester_id: str) -> account_models.User:
    if approver_user_id == requester_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RETENTION_SEPARATION_OF_DUTIES_REQUIRED",
                "message": "Disposition requester cannot be the assigned approver.",
            },
        )
    user = (
        db.query(account_models.User)
        .filter(
            account_models.User.id == approver_user_id,
            account_models.User.amo_id == tenant.amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .first()
    )
    if not user or not is_decision_approver(user):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "RETENTION_APPROVER_INVALID",
                "message": "Select an active authorized Document Control disposition approver.",
            },
        )
    return user


@router.get("/t/{tenant_slug}/documents/{manual_id}/retention")
def list_retention_accountable(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    get_manual(db, tenant, manual_id)
    rows = (
        db.query(rm.DocumentRetentionDisposition)
        .filter(
            rm.DocumentRetentionDisposition.tenant_id == tenant.amo_id,
            rm.DocumentRetentionDisposition.manual_id == manual_id,
        )
        .order_by(rm.DocumentRetentionDisposition.created_at.desc(), rm.DocumentRetentionDisposition.id.desc())
        .limit(500)
        .all()
    )
    return {"items": [_retention_payload(row) for row in rows], "total": len(rows), "bounded": True, "limit": 500}


@router.get("/t/{tenant_slug}/retention-approvers")
def list_retention_approvers(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    users = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == tenant.amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
            account_models.User.id != current_user.id,
        )
        .order_by(account_models.User.full_name.asc(), account_models.User.email.asc())
        .all()
    )
    items = []
    for user in users:
        if not is_decision_approver(user):
            continue
        role = getattr(getattr(user, "role", None), "value", getattr(user, "role", None))
        items.append(
            {
                "id": str(user.id),
                "label": str(user.full_name or user.email),
                "email": str(user.email),
                "role": str(role or "APPROVER"),
            }
        )
    return {"items": items, "total": len(items), "bounded": True, "limit": 500}


@router.get("/t/{tenant_slug}/retention-work")
def retention_work(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    rows = (
        db.query(rm.DocumentRetentionDisposition)
        .filter(
            rm.DocumentRetentionDisposition.tenant_id == tenant.amo_id,
            or_(
                (
                    (rm.DocumentRetentionDisposition.status == "DISPOSITION_REQUESTED")
                    & (rm.DocumentRetentionDisposition.approver_user_id == current_user.id)
                ),
                (
                    (rm.DocumentRetentionDisposition.status == "APPROVED")
                    & (rm.DocumentRetentionDisposition.requested_by_user_id == current_user.id)
                ),
            ),
        )
        .order_by(rm.DocumentRetentionDisposition.updated_at.asc(), rm.DocumentRetentionDisposition.id.asc())
        .limit(100)
        .all()
    )
    manual_ids = {str(row.manual_id) for row in rows}
    manuals = {
        str(row.id): row
        for row in db.query(manual_models.Manual).filter(manual_models.Manual.id.in_(manual_ids)).all()
    } if manual_ids else {}
    items = []
    for row in rows:
        approval = row.status == "DISPOSITION_REQUESTED"
        manual = manuals.get(str(row.manual_id))
        code = str(getattr(manual, "code", None) or "Document")
        items.append(
            {
                "id": row.id,
                "kind": "RETENTION_APPROVAL" if approval else "RETENTION_EXECUTION",
                "title": f"{'Approve disposition' if approval else 'Record disposition'} · {code}",
                "detail": row.source_label,
                "status": row.status,
                "priority": "HIGH" if approval else "NORMAL",
                "manual_id": row.manual_id,
                "target_path": _notification_action_url(tenant.slug, row),
                "due_at": row.retention_until.isoformat() if row.retention_until else None,
            }
        )
    return {"items": items, "total": len(items), "bounded": True, "limit": 100}


@router.patch("/t/{tenant_slug}/retention/{retention_id}/hold")
def update_retention_hold_accountable(
    tenant_slug: str,
    retention_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_decision_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _row(db, tenant_id=tenant.amo_id, retention_id=retention_id)
    if row.status == "DISPOSED":
        raise HTTPException(status_code=409, detail="Disposed retention evidence is immutable")
    legal_hold = bool(payload.get("legal_hold"))
    reason = str(payload.get("reason") or "").strip()
    if legal_hold and not reason:
        raise HTTPException(status_code=422, detail="Legal hold requires a reason")
    before = _retention_payload(row)
    row.legal_hold = legal_hold
    row.hold_reason = reason or None
    if legal_hold:
        row.status = "HOLD"
        row.approver_user_id = None
        row.approved_by_user_id = None
        row.approved_at = None
    elif row.status == "HOLD":
        row.status = _due_status(row.retention_until)
    row.updated_at = utcnow()
    after = _retention_payload(row)
    audit(db, tenant, request, "document.retention.hold_updated", "document_retention_disposition", row.id, {"before": before, "after": after})
    db.commit()
    return after


@router.post("/t/{tenant_slug}/retention/{retention_id}/request-disposition")
def request_disposition_accountable(
    tenant_slug: str,
    retention_id: str,
    payload: RetentionRequestWithApprover,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _row(db, tenant_id=tenant.amo_id, retention_id=retention_id)
    if row.legal_hold or row.status == "HOLD":
        raise HTTPException(status_code=409, detail="Disposition is blocked by legal hold")
    if row.status not in {"ACTIVE", "DUE", "REJECTED"}:
        raise HTTPException(status_code=409, detail=f"Disposition cannot be requested from {row.status}")
    approver = _assigned_approver(
        db,
        tenant=tenant,
        approver_user_id=payload.approver_user_id,
        requester_id=str(current_user.id),
    )
    now = utcnow()
    row.status = "DISPOSITION_REQUESTED"
    row.justification = payload.justification.strip()
    row.requested_by_user_id = current_user.id
    row.approver_user_id = approver.id
    row.requested_at = now
    row.approved_by_user_id = None
    row.approved_at = None
    row.updated_at = now
    audit(db, tenant, request, "document.retention.disposition_requested", "document_retention_disposition", row.id, _retention_payload(row))
    _queue_notification(
        db,
        tenant=tenant,
        user_id=str(approver.id),
        row=row,
        event="REQUESTED",
        title="Document disposition approval required",
        body=f"Review the requested disposition for {row.source_label}.",
    )
    db.commit()
    return _retention_payload(row)


@router.post("/t/{tenant_slug}/retention/{retention_id}/decision")
def decide_disposition_accountable(
    tenant_slug: str,
    retention_id: str,
    payload: RetentionDecision,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_decision_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _row(db, tenant_id=tenant.amo_id, retention_id=retention_id)
    if row.status != "DISPOSITION_REQUESTED":
        raise HTTPException(status_code=409, detail="Only a requested disposition can be approved or rejected")
    if row.legal_hold:
        raise HTTPException(status_code=409, detail="Disposition approval is blocked by legal hold")
    if not row.approver_user_id:
        raise HTTPException(status_code=409, detail={"code": "RETENTION_APPROVER_ASSIGNMENT_REQUIRED", "message": "Disposition has no assigned approver."})
    if str(row.approver_user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Only the assigned disposition approver may record this decision")
    if row.requested_by_user_id and str(row.requested_by_user_id) == str(current_user.id):
        raise HTTPException(status_code=409, detail={"code": "RETENTION_SEPARATION_OF_DUTIES_REQUIRED", "message": "The requester cannot approve their own disposition request."})
    now = utcnow()
    row.justification = payload.justification.strip()
    approved = payload.decision == "APPROVE"
    row.status = "APPROVED" if approved else "REJECTED"
    row.approved_by_user_id = current_user.id if approved else None
    row.approved_at = now if approved else None
    row.updated_at = now
    audit(db, tenant, request, f"document.retention.{payload.decision.lower()}", "document_retention_disposition", row.id, _retention_payload(row))
    _queue_notification(
        db,
        tenant=tenant,
        user_id=str(row.requested_by_user_id) if row.requested_by_user_id else None,
        row=row,
        event="APPROVED" if approved else "REJECTED",
        title="Document disposition approved" if approved else "Document disposition rejected",
        body=(
            f"Disposition for {row.source_label} is approved. Retain the disposition certificate and record execution."
            if approved
            else f"Disposition for {row.source_label} was rejected. Review the decision and correct the request before resubmission."
        ),
    )
    db.commit()
    return _retention_payload(row)
