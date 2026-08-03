from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models


# Included by the canonical /accounts/admin router. The resulting API surface is
# /accounts/admin/admin-profile/{amo_code}/...
router = APIRouter(prefix="/admin-profile", tags=["admin_profile"])
SESSION_DURATION_MINUTES = 30
REQUIRED_APPROVALS = 2


class AdminGrantRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    grant_type: Literal["PERMANENT", "TEMPORARY"]
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    reason: str = Field(min_length=8, max_length=1000)


class AdminGrantDecision(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _normalise_role(user: models.User) -> str:
    value = getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))
    return str(value or "").upper()


def _is_implicit_admin(user: models.User) -> bool:
    if getattr(user, "is_superuser", False):
        return False
    return bool(getattr(user, "is_amo_admin", False) or _normalise_role(user) == "AMO_ADMIN")


def _is_management_approver(user: models.User) -> bool:
    if _is_implicit_admin(user):
        return True
    role = _normalise_role(user)
    title = str(getattr(user, "position_title", "") or "").lower()
    return (
        role in {"QUALITY_MANAGER", "SAFETY_MANAGER"}
        or "accountable manager" in title
        or "human resources manager" in title
        or title.strip() == "hr manager"
    )


def _ensure_schema(db: Session) -> None:
    """Create the governance tables for development databases.

    A matching Alembic revision is maintained separately. These idempotent DDL
    statements keep a freshly checked-out development database usable before the
    migration command is run and use portable TIMESTAMP declarations for SQLite
    and PostgreSQL test environments.
    """
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS admin_access_grants (
            id VARCHAR(36) PRIMARY KEY,
            amo_id VARCHAR(36) NOT NULL,
            user_id VARCHAR(36) NOT NULL,
            grant_type VARCHAR(16) NOT NULL,
            valid_from TIMESTAMP NULL,
            valid_until TIMESTAMP NULL,
            status VARCHAR(16) NOT NULL,
            reason TEXT NOT NULL,
            requested_by_user_id VARCHAR(36) NOT NULL,
            activated_at TIMESTAMP NULL,
            revoked_at TIMESTAMP NULL,
            revoked_by_user_id VARCHAR(36) NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS admin_access_grant_approvals (
            id VARCHAR(36) PRIMARY KEY,
            grant_id VARCHAR(36) NOT NULL,
            approver_user_id VARCHAR(36) NOT NULL,
            decision VARCHAR(16) NOT NULL,
            comment TEXT NULL,
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT uq_admin_grant_approver UNIQUE (grant_id, approver_user_id)
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS admin_profile_sessions (
            id VARCHAR(36) PRIMARY KEY,
            amo_id VARCHAR(36) NOT NULL,
            user_id VARCHAR(36) NOT NULL,
            grant_id VARCHAR(36) NULL,
            activated_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS admin_access_events (
            id VARCHAR(36) PRIMARY KEY,
            amo_id VARCHAR(36) NOT NULL,
            actor_user_id VARCHAR(36) NOT NULL,
            subject_user_id VARCHAR(36) NULL,
            grant_id VARCHAR(36) NULL,
            session_id VARCHAR(36) NULL,
            event_type VARCHAR(64) NOT NULL,
            detail TEXT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_grants_amo_user_status ON admin_access_grants (amo_id, user_id, status)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_profile_sessions_amo_user ON admin_profile_sessions (amo_id, user_id, expires_at)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_access_events_amo_created ON admin_access_events (amo_id, created_at)"))
    db.flush()


def _record_event(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    event_type: str,
    subject_user_id: str | None = None,
    grant_id: str | None = None,
    session_id: str | None = None,
    detail: str | None = None,
) -> None:
    db.execute(
        text("""
            INSERT INTO admin_access_events (
                id, amo_id, actor_user_id, subject_user_id, grant_id,
                session_id, event_type, detail, created_at
            ) VALUES (
                :id, :amo_id, :actor_user_id, :subject_user_id, :grant_id,
                :session_id, :event_type, :detail, :created_at
            )
        """),
        {
            "id": str(uuid4()),
            "amo_id": amo_id,
            "actor_user_id": actor_user_id,
            "subject_user_id": subject_user_id,
            "grant_id": grant_id,
            "session_id": session_id,
            "event_type": event_type,
            "detail": detail,
            "created_at": _utcnow(),
        },
    )


def _resolve_amo(db: Session, amo_code: str) -> models.AMO:
    amo = (
        db.query(models.AMO)
        .filter(
            models.AMO.is_active.is_(True),
            (models.AMO.amo_code == amo_code) | (models.AMO.login_slug == amo_code),
        )
        .first()
    )
    if not amo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AMO tenant was not found.")
    return amo


def _assert_tenant_member(user: models.User, amo: models.AMO) -> None:
    if getattr(user, "is_superuser", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform superusers must use the platform support-session control plane.",
        )
    effective_amo_id = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if not effective_amo_id or str(effective_amo_id) != str(amo.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a member of this AMO tenant.")


def _approval_count(db: Session, grant_id: str) -> int:
    value = db.execute(
        text("""
            SELECT COUNT(DISTINCT approver_user_id)
            FROM admin_access_grant_approvals
            WHERE grant_id = :grant_id AND decision = 'APPROVED'
        """),
        {"grant_id": grant_id},
    ).scalar()
    return int(value or 0)


def _eligible_grant(db: Session, *, amo_id: str, user_id: str, now: datetime) -> dict[str, Any] | None:
    row = db.execute(
        text("""
            SELECT id, grant_type, valid_from, valid_until, reason
            FROM admin_access_grants
            WHERE amo_id = :amo_id
              AND user_id = :user_id
              AND status = 'ACTIVE'
              AND (valid_from IS NULL OR valid_from <= :now)
              AND (valid_until IS NULL OR valid_until > :now)
            ORDER BY CASE WHEN valid_until IS NULL THEN 1 ELSE 0 END, valid_until DESC
            LIMIT 1
        """),
        {"amo_id": amo_id, "user_id": user_id, "now": now},
    ).mappings().first()
    return dict(row) if row else None


def _active_session(db: Session, *, amo_id: str, user_id: str, now: datetime) -> dict[str, Any] | None:
    row = db.execute(
        text("""
            SELECT id, grant_id, activated_at, expires_at
            FROM admin_profile_sessions
            WHERE amo_id = :amo_id
              AND user_id = :user_id
              AND revoked_at IS NULL
              AND expires_at > :now
            ORDER BY activated_at DESC
            LIMIT 1
        """),
        {"amo_id": amo_id, "user_id": user_id, "now": now},
    ).mappings().first()
    return dict(row) if row else None


def _state(db: Session, *, amo: models.AMO, user: models.User) -> dict[str, Any]:
    _ensure_schema(db)
    now = _utcnow()
    db.execute(
        text("""
            UPDATE admin_profile_sessions
            SET revoked_at = :now
            WHERE amo_id = :amo_id
              AND user_id = :user_id
              AND revoked_at IS NULL
              AND expires_at <= :now
        """),
        {"now": now, "amo_id": str(amo.id), "user_id": str(user.id)},
    )
    implicit = _is_implicit_admin(user)
    grant = None if implicit else _eligible_grant(db, amo_id=str(amo.id), user_id=str(user.id), now=now)
    session = _active_session(db, amo_id=str(amo.id), user_id=str(user.id), now=now)
    eligible = implicit or grant is not None
    return {
        "eligible": eligible,
        "active": bool(eligible and session),
        "session_id": session.get("id") if session else None,
        "expires_at": session.get("expires_at") if session else None,
        "grant_type": "PERMANENT" if implicit else (grant.get("grant_type") if grant else None),
        "reason": "Existing AMO administrator" if implicit else (grant.get("reason") if grant else None),
    }


def _require_active_profile(db: Session, *, amo: models.AMO, user: models.User) -> dict[str, Any]:
    result = _state(db, amo=amo, user=user)
    if not result["active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Activate Admin profile before performing this administration action.",
        )
    return result


def _require_governance_approver(db: Session, *, amo: models.AMO, user: models.User) -> None:
    if _is_management_approver(user):
        return
    _require_active_profile(db, amo=amo, user=user)


@router.get("/{amo_code}/state")
def admin_profile_state(
    amo_code: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    amo = _resolve_amo(db, amo_code)
    _assert_tenant_member(current_user, amo)
    result = _state(db, amo=amo, user=current_user)
    db.commit()
    return result


@router.post("/{amo_code}/activate")
def activate_admin_profile(
    amo_code: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    amo = _resolve_amo(db, amo_code)
    _assert_tenant_member(current_user, amo)
    _ensure_schema(db)
    now = _utcnow()
    implicit = _is_implicit_admin(current_user)
    grant = None if implicit else _eligible_grant(db, amo_id=str(amo.id), user_id=str(current_user.id), now=now)
    if not implicit and not grant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No approved administrator grant is active for this user.")

    db.execute(
        text("""
            UPDATE admin_profile_sessions
            SET revoked_at = :now
            WHERE amo_id = :amo_id AND user_id = :user_id AND revoked_at IS NULL
        """),
        {"now": now, "amo_id": str(amo.id), "user_id": str(current_user.id)},
    )
    expires_at = now + timedelta(minutes=SESSION_DURATION_MINUTES)
    grant_valid_until = _as_utc(grant.get("valid_until")) if grant else None
    if grant_valid_until and grant_valid_until < expires_at:
        expires_at = grant_valid_until
    session_id = str(uuid4())
    db.execute(
        text("""
            INSERT INTO admin_profile_sessions (
                id, amo_id, user_id, grant_id, activated_at,
                expires_at, revoked_at, created_at
            ) VALUES (
                :id, :amo_id, :user_id, :grant_id, :activated_at,
                :expires_at, NULL, :created_at
            )
        """),
        {
            "id": session_id,
            "amo_id": str(amo.id),
            "user_id": str(current_user.id),
            "grant_id": grant.get("id") if grant else None,
            "activated_at": now,
            "expires_at": expires_at,
            "created_at": now,
        },
    )
    _record_event(
        db,
        amo_id=str(amo.id),
        actor_user_id=str(current_user.id),
        subject_user_id=str(current_user.id),
        grant_id=grant.get("id") if grant else None,
        session_id=session_id,
        event_type="ADMIN_PROFILE_ACTIVATED",
    )
    db.commit()
    return _state(db, amo=amo, user=current_user)


@router.post("/{amo_code}/deactivate")
def deactivate_admin_profile(
    amo_code: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    amo = _resolve_amo(db, amo_code)
    _assert_tenant_member(current_user, amo)
    _ensure_schema(db)
    now = _utcnow()
    db.execute(
        text("""
            UPDATE admin_profile_sessions
            SET revoked_at = :now
            WHERE amo_id = :amo_id AND user_id = :user_id AND revoked_at IS NULL
        """),
        {"now": now, "amo_id": str(amo.id), "user_id": str(current_user.id)},
    )
    _record_event(
        db,
        amo_id=str(amo.id),
        actor_user_id=str(current_user.id),
        subject_user_id=str(current_user.id),
        event_type="ADMIN_PROFILE_DEACTIVATED",
    )
    db.commit()
    return _state(db, amo=amo, user=current_user)


@router.get("/{amo_code}/grants")
def list_admin_grants(
    amo_code: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    amo = _resolve_amo(db, amo_code)
    _assert_tenant_member(current_user, amo)
    _require_active_profile(db, amo=amo, user=current_user)
    rows = db.execute(
        text("""
            SELECT g.*,
                   (
                       SELECT COUNT(DISTINCT a.approver_user_id)
                       FROM admin_access_grant_approvals a
                       WHERE a.grant_id = g.id AND a.decision = 'APPROVED'
                   ) AS approval_count
            FROM admin_access_grants g
            WHERE g.amo_id = :amo_id
            ORDER BY g.created_at DESC
            LIMIT 500
        """),
        {"amo_id": str(amo.id)},
    ).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/{amo_code}/grants", status_code=status.HTTP_201_CREATED)
def request_admin_grant(
    amo_code: str,
    payload: AdminGrantRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    amo = _resolve_amo(db, amo_code)
    _assert_tenant_member(current_user, amo)
    _require_active_profile(db, amo=amo, user=current_user)
    target = (
        db.query(models.User)
        .filter(models.User.id == payload.user_id, models.User.amo_id == amo.id)
        .first()
    )
    if not target or not target.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active tenant user was not found.")

    valid_from = _as_utc(payload.valid_from) or _utcnow()
    valid_until = _as_utc(payload.valid_until)
    if payload.grant_type == "TEMPORARY" and not valid_until:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Temporary administrator grants require an expiry time.",
        )
    if valid_until and valid_until <= valid_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Grant expiry must be later than its start time.",
        )

    now = _utcnow()
    grant_id = str(uuid4())
    db.execute(
        text("""
            INSERT INTO admin_access_grants (
                id, amo_id, user_id, grant_type, valid_from, valid_until,
                status, reason, requested_by_user_id, activated_at,
                revoked_at, revoked_by_user_id, created_at, updated_at
            ) VALUES (
                :id, :amo_id, :user_id, :grant_type, :valid_from, :valid_until,
                'PENDING', :reason, :requested_by_user_id, NULL,
                NULL, NULL, :created_at, :updated_at
            )
        """),
        {
            "id": grant_id,
            "amo_id": str(amo.id),
            "user_id": str(target.id),
            "grant_type": payload.grant_type,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "reason": payload.reason.strip(),
            "requested_by_user_id": str(current_user.id),
            "created_at": now,
            "updated_at": now,
        },
    )
    _record_event(
        db,
        amo_id=str(amo.id),
        actor_user_id=str(current_user.id),
        subject_user_id=str(target.id),
        grant_id=grant_id,
        event_type="ADMIN_GRANT_REQUESTED",
        detail=payload.reason.strip(),
    )
    db.commit()
    return {
        "id": grant_id,
        "status": "PENDING",
        "approval_count": 0,
        "required_approvals": REQUIRED_APPROVALS,
    }


@router.post("/{amo_code}/grants/{grant_id}/approve")
def approve_admin_grant(
    amo_code: str,
    grant_id: str,
    payload: AdminGrantDecision,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    amo = _resolve_amo(db, amo_code)
    _assert_tenant_member(current_user, amo)
    _ensure_schema(db)
    _require_governance_approver(db, amo=amo, user=current_user)
    grant = db.execute(
        text("SELECT * FROM admin_access_grants WHERE id = :grant_id AND amo_id = :amo_id"),
        {"grant_id": grant_id, "amo_id": str(amo.id)},
    ).mappings().first()
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Administrator grant request was not found.")
    if grant["status"] not in {"PENDING", "ACTIVE"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This administrator grant is no longer awaiting approval.")
    if str(grant["requested_by_user_id"]) == str(current_user.id) or str(grant["user_id"]) == str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The requester and grantee cannot approve this grant.")

    now = _utcnow()
    existing = db.execute(
        text("""
            SELECT 1 FROM admin_access_grant_approvals
            WHERE grant_id = :grant_id AND approver_user_id = :approver_user_id
        """),
        {"grant_id": grant_id, "approver_user_id": str(current_user.id)},
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This manager has already approved the grant.")

    db.execute(
        text("""
            INSERT INTO admin_access_grant_approvals (
                id, grant_id, approver_user_id, decision, comment, created_at
            ) VALUES (
                :id, :grant_id, :approver_user_id, 'APPROVED', :comment, :created_at
            )
        """),
        {
            "id": str(uuid4()),
            "grant_id": grant_id,
            "approver_user_id": str(current_user.id),
            "comment": payload.comment,
            "created_at": now,
        },
    )
    count = _approval_count(db, grant_id)
    next_status = "ACTIVE" if count >= REQUIRED_APPROVALS else "PENDING"
    if next_status == "ACTIVE":
        db.execute(
            text("""
                UPDATE admin_access_grants
                SET status = 'ACTIVE', activated_at = :now, updated_at = :now
                WHERE id = :grant_id
            """),
            {"now": now, "grant_id": grant_id},
        )
    _record_event(
        db,
        amo_id=str(amo.id),
        actor_user_id=str(current_user.id),
        subject_user_id=str(grant["user_id"]),
        grant_id=grant_id,
        event_type="ADMIN_GRANT_APPROVED",
        detail=payload.comment,
    )
    db.commit()
    return {
        "id": grant_id,
        "status": next_status,
        "approval_count": count,
        "required_approvals": REQUIRED_APPROVALS,
    }


@router.post("/{amo_code}/grants/{grant_id}/revoke")
def revoke_admin_grant(
    amo_code: str,
    grant_id: str,
    payload: AdminGrantDecision,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    amo = _resolve_amo(db, amo_code)
    _assert_tenant_member(current_user, amo)
    _ensure_schema(db)
    _require_governance_approver(db, amo=amo, user=current_user)
    grant = db.execute(
        text("SELECT id, user_id FROM admin_access_grants WHERE id = :grant_id AND amo_id = :amo_id"),
        {"grant_id": grant_id, "amo_id": str(amo.id)},
    ).mappings().first()
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Administrator grant was not found.")

    now = _utcnow()
    db.execute(
        text("""
            UPDATE admin_access_grants
            SET status = 'REVOKED', revoked_at = :now,
                revoked_by_user_id = :actor, updated_at = :now
            WHERE id = :grant_id
        """),
        {"now": now, "actor": str(current_user.id), "grant_id": grant_id},
    )
    db.execute(
        text("""
            UPDATE admin_profile_sessions
            SET revoked_at = :now
            WHERE amo_id = :amo_id AND user_id = :user_id AND revoked_at IS NULL
        """),
        {"now": now, "amo_id": str(amo.id), "user_id": str(grant["user_id"])},
    )
    _record_event(
        db,
        amo_id=str(amo.id),
        actor_user_id=str(current_user.id),
        subject_user_id=str(grant["user_id"]),
        grant_id=grant_id,
        event_type="ADMIN_GRANT_REVOKED",
        detail=payload.comment,
    )
    db.commit()
    return {"id": grant_id, "status": "REVOKED"}
