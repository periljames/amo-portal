"""Self-service tenant access-profile elevation requests.

This workflow changes portal access only.  It cannot request or manufacture a
prescribed management appointment, tenant-administrator authority, licence,
stamp or certifying authorization.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_db
from amodb.security import get_current_active_user, require_admin

from . import access_control, models, role_registry
from .access_realtime import publish_access_sync


context_router = APIRouter(tags=["accounts_access_requests"])
admin_router = APIRouter(tags=["accounts_access_requests"])

_REQUEST_STATUSES = {"PENDING", "APPROVED", "DENIED", "CANCELLED"}
_PROTECTED_BASE_ROLES = frozenset(
    set(role_registry.REGULATED_MANAGEMENT_ROLE_KEYS) | {"SUPERUSER", "AMO_ADMIN"}
)


class AccessElevationRequestCreate(BaseModel):
    requested_profile_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=8, max_length=1000)


class AccessElevationDecision(BaseModel):
    decision: Literal["APPROVE", "DENY"]
    note: str | None = Field(default=None, max_length=1000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tenant_id(current_user: models.User) -> str:
    value = getattr(current_user, "effective_amo_id", None) or getattr(current_user, "amo_id", None)
    if not value:
        raise HTTPException(status_code=409, detail="Select an AMO tenant before managing access.")
    return str(value)


def _requestable_profile(db: Session, *, amo_id: str, profile_id: str) -> models.AuthRoleDefinition:
    row = db.query(models.AuthRoleDefinition).filter(
        models.AuthRoleDefinition.id == profile_id,
        models.AuthRoleDefinition.amo_id == amo_id,
        models.AuthRoleDefinition.is_active.is_(True),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Requested access profile was not found or is inactive.")
    base_role = role_registry.canonical_role_key(row.base_role_key) or str(row.base_role_key or "").upper()
    if bool(row.is_regulated) or base_role in _PROTECTED_BASE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                "This profile represents protected management or administration authority and cannot be requested "
                "through access elevation. Use the governed appointment or Administrator Profile workflow."
            ),
        )
    return row


def _request_rows(db: Session, *, amo_id: str, user_id: str | None = None, request_status: str | None = None):
    where = ["r.amo_id = :amo_id"]
    params: dict[str, object] = {"amo_id": amo_id}
    if user_id:
        where.append("r.user_id = :user_id")
        params["user_id"] = user_id
    if request_status:
        where.append("r.status = :request_status")
        params["request_status"] = request_status
    rows = db.execute(text(f"""
        SELECT
            r.id, r.amo_id, r.user_id, r.current_profile_id, r.requested_profile_id,
            r.requested_by_user_id, r.reason, r.status, r.decision_note,
            r.decided_by_user_id, r.created_at, r.updated_at, r.decided_at,
            u.full_name AS user_name, u.email AS user_email, u.staff_code AS staff_code,
            cp.display_name AS current_profile_name,
            rp.display_name AS requested_profile_name,
            rp.tenant_code AS requested_profile_code,
            rp.base_role_key AS requested_base_role_key,
            du.full_name AS decided_by_name
        FROM user_access_profile_requests r
        JOIN users u ON u.id = r.user_id
        LEFT JOIN auth_role_definitions cp ON cp.id = r.current_profile_id
        JOIN auth_role_definitions rp ON rp.id = r.requested_profile_id
        LEFT JOIN users du ON du.id = r.decided_by_user_id
        WHERE {' AND '.join(where)}
        ORDER BY r.created_at DESC
        LIMIT 250
    """), params).mappings().all()
    return [dict(row) for row in rows]


@context_router.get("/access-elevation-requests")
def list_my_access_elevation_requests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    tenant_id = _tenant_id(current_user)
    return {"items": _request_rows(db, amo_id=tenant_id, user_id=str(current_user.id))}


@context_router.post(
    "/access-elevation-requests",
    status_code=status.HTTP_201_CREATED,
)
def request_access_elevation(
    payload: AccessElevationRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    tenant_id = _tenant_id(current_user)
    access_control.attach_user_access(db, current_user)
    target = _requestable_profile(db, amo_id=tenant_id, profile_id=payload.requested_profile_id)
    current_profile_id = str(getattr(current_user, "access_profile_id", "") or "") or None
    if current_profile_id == str(target.id):
        raise HTTPException(status_code=409, detail="You already use this access profile.")

    existing = db.execute(text("""
        SELECT id FROM user_access_profile_requests
        WHERE amo_id = :amo_id AND user_id = :user_id AND status = 'PENDING'
        LIMIT 1
    """), {"amo_id": tenant_id, "user_id": str(current_user.id)}).scalar()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="You already have a pending access request. Cancel it or wait for an administrator decision.",
        )

    now = _utcnow()
    request_id = str(uuid4())
    reason = payload.reason.strip()
    try:
        db.execute(text("""
            INSERT INTO user_access_profile_requests (
                id, amo_id, user_id, current_profile_id, requested_profile_id,
                requested_by_user_id, reason, status, created_at, updated_at
            ) VALUES (
                :id, :amo_id, :user_id, :current_profile_id, :requested_profile_id,
                :requested_by_user_id, :reason, 'PENDING', :created_at, :updated_at
            )
        """), {
            "id": request_id,
            "amo_id": tenant_id,
            "user_id": str(current_user.id),
            "current_profile_id": current_profile_id,
            "requested_profile_id": str(target.id),
            "requested_by_user_id": str(current_user.id),
            "reason": reason,
            "created_at": now,
            "updated_at": now,
        })
        audit_services.log_event(
            db,
            amo_id=tenant_id,
            actor_user_id=str(current_user.id),
            entity_type="accounts.access_elevation_request",
            entity_id=request_id,
            action="REQUESTED",
            after={
                "requested_profile_id": str(target.id),
                "current_profile_id": current_profile_id,
                "reason": reason,
                "status": "PENDING",
            },
            metadata={"module": "accounts", "subject_user_id": str(current_user.id)},
            critical=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    publish_access_sync(
        amo_id=tenant_id,
        action="REQUESTED",
        entity_id=request_id,
        actor_user_id=str(current_user.id),
        subject_user_id=str(current_user.id),
        profile_id=str(target.id),
        request_id=request_id,
        status="PENDING",
    )
    return _request_rows(db, amo_id=tenant_id, user_id=str(current_user.id))[0]


@context_router.post("/access-elevation-requests/{request_id}/cancel")
def cancel_access_elevation_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    tenant_id = _tenant_id(current_user)
    now = _utcnow()
    result = db.execute(text("""
        UPDATE user_access_profile_requests
        SET status = 'CANCELLED', updated_at = :now, decided_at = :now,
            decided_by_user_id = :user_id,
            decision_note = COALESCE(decision_note, 'Cancelled by requester')
        WHERE id = :request_id AND amo_id = :amo_id AND user_id = :user_id
          AND status = 'PENDING'
    """), {
        "now": now,
        "user_id": str(current_user.id),
        "request_id": request_id,
        "amo_id": tenant_id,
    })
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Only your own pending access request can be cancelled.")
    audit_services.log_event(
        db,
        amo_id=tenant_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.access_elevation_request",
        entity_id=request_id,
        action="CANCELLED",
        after={"status": "CANCELLED"},
        metadata={"module": "accounts", "subject_user_id": str(current_user.id)},
        critical=True,
    )
    db.commit()
    publish_access_sync(
        amo_id=tenant_id,
        action="CANCELLED",
        entity_id=request_id,
        actor_user_id=str(current_user.id),
        subject_user_id=str(current_user.id),
        request_id=request_id,
        status="CANCELLED",
    )
    return {"id": request_id, "status": "CANCELLED"}


@admin_router.get("/access-elevation-requests")
def list_tenant_access_elevation_requests(
    request_status: str | None = Query(default="PENDING", alias="status"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    tenant_id = _tenant_id(current_user)
    normalized = str(request_status or "").upper() or None
    if normalized and normalized not in _REQUEST_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown access request status.")
    return {"items": _request_rows(db, amo_id=tenant_id, request_status=normalized)}


@admin_router.post("/access-elevation-requests/{request_id}/decision")
def decide_access_elevation_request(
    request_id: str,
    payload: AccessElevationDecision,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    tenant_id = _tenant_id(current_user)
    row = db.execute(text("""
        SELECT id, user_id, current_profile_id, requested_profile_id, reason, status
        FROM user_access_profile_requests
        WHERE id = :request_id AND amo_id = :amo_id
        LIMIT 1
    """), {"request_id": request_id, "amo_id": tenant_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Access elevation request not found.")
    if str(row["status"]) != "PENDING":
        raise HTTPException(status_code=409, detail=f"This access request is already {str(row['status']).lower()}.")

    user = db.query(models.User).filter(
        models.User.id == str(row["user_id"]),
        models.User.amo_id == tenant_id,
        models.User.is_active.is_(True),
    ).first()
    if user is None:
        raise HTTPException(status_code=409, detail="The requesting user is no longer an active tenant user.")

    note = (payload.note or "").strip() or None
    now = _utcnow()
    decision_status = "APPROVED" if payload.decision == "APPROVE" else "DENIED"
    profile_id = str(row["requested_profile_id"])

    try:
        if decision_status == "APPROVED":
            target = _requestable_profile(db, amo_id=tenant_id, profile_id=profile_id)
            access_control.assign_primary_access_profile(
                db,
                user=user,
                profile_id=str(target.id),
                actor_user_id=str(current_user.id),
            )

        result = db.execute(text("""
            UPDATE user_access_profile_requests
            SET status = :status, decision_note = :decision_note,
                decided_by_user_id = :decided_by_user_id,
                decided_at = :decided_at, updated_at = :updated_at
            WHERE id = :request_id AND amo_id = :amo_id AND status = 'PENDING'
        """), {
            "status": decision_status,
            "decision_note": note,
            "decided_by_user_id": str(current_user.id),
            "decided_at": now,
            "updated_at": now,
            "request_id": request_id,
            "amo_id": tenant_id,
        })
        if result.rowcount != 1:
            raise HTTPException(status_code=409, detail="This access request changed before your decision was saved.")

        if decision_status == "APPROVED":
            audit_services.log_event(
                db,
                amo_id=tenant_id,
                actor_user_id=str(current_user.id),
                entity_type="accounts.user_access_profile",
                entity_id=str(user.id),
                action="ASSIGNED_FROM_REQUEST",
                before={"access_profile_id": row["current_profile_id"]},
                after={"access_profile_id": profile_id, "request_id": request_id},
                metadata={"module": "accounts", "subject_user_id": str(user.id)},
                critical=True,
            )
        audit_services.log_event(
            db,
            amo_id=tenant_id,
            actor_user_id=str(current_user.id),
            entity_type="accounts.access_elevation_request",
            entity_id=request_id,
            action=decision_status,
            before={"status": "PENDING"},
            after={"status": decision_status, "decision_note": note},
            metadata={"module": "accounts", "subject_user_id": str(user.id)},
            critical=True,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    publish_access_sync(
        amo_id=tenant_id,
        action=decision_status,
        entity_id=request_id,
        actor_user_id=str(current_user.id),
        subject_user_id=str(user.id),
        profile_id=profile_id,
        request_id=request_id,
        status=decision_status,
    )
    items = _request_rows(db, amo_id=tenant_id)
    return next((item for item in items if str(item["id"]) == request_id), {"id": request_id, "status": decision_status})
