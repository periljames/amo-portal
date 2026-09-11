from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models, role_registry
from .tenant_authority import is_standing_admin, is_tenant_admin, tenant_member, can_revoke_administrator


# Included by the canonical /accounts/admin router. The resulting API surface is
# /accounts/admin/admin-profile/{amo_code}/...
router = APIRouter(prefix="/admin-profile", tags=["admin_profile"])
SESSION_DURATION_MINUTES = 30
REQUIRED_APPROVALS = 1
REQUIRED_SCHEMA_TABLES = frozenset(
    {
        "admin_access_grants",
        "admin_access_grant_approvals",
        "admin_profile_sessions",
        "admin_access_events",
    }
)
REQUIRED_SESSION_COLUMNS = frozenset({"auth_session_id"})
REQUIRED_APPROVAL_COLUMNS = frozenset({"approver_role"})


class AdminGrantRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    grant_type: Literal["PERMANENT", "TEMPORARY"]
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    reason: str = Field(min_length=8, max_length=1000)


class AdminGrantDecision(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class AdminRemovalDecision(AdminGrantDecision):
    deactivate_account: bool = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _normalise_role(user: models.User) -> str:
    value = getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))
    return role_registry.canonical_role_key(value) or str(value or "").upper()


def _is_implicit_admin(user: models.User) -> bool:
    return is_standing_admin(user)


def _is_management_approver(user: models.User) -> bool:
    return tenant_member(user) and _normalise_role(user) == "ACCOUNTABLE_EXECUTIVE"


def _auth_session_id(user: models.User) -> str:
    value = str(
        getattr(user, "auth_session_id", None)
        or getattr(user, "_auth_session_id", None)
        or ""
    ).strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication session identity is unavailable. Sign in again.",
        )
    return value


def _ensure_schema(db: Session) -> None:
    """Fail closed until the governed Admin Profile migration is installed."""
    try:
        schema = inspect(db.get_bind())
        existing = set(schema.get_table_names())
        session_columns = (
            {str(column["name"]) for column in schema.get_columns("admin_profile_sessions")}
            if "admin_profile_sessions" in existing
            else set()
        )
        approval_columns = (
            {str(column["name"]) for column in schema.get_columns("admin_access_grant_approvals")}
            if "admin_access_grant_approvals" in existing
            else set()
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrator profile schema could not be verified.",
        ) from exc

    missing = sorted(REQUIRED_SCHEMA_TABLES - existing)
    missing_columns = sorted(REQUIRED_SESSION_COLUMNS - session_columns)
    missing_approval_columns = sorted(REQUIRED_APPROVAL_COLUMNS - approval_columns)
    if missing or missing_columns or missing_approval_columns:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ADMIN_PROFILE_SCHEMA_NOT_MIGRATED",
                "message": "Run Alembic migrations before using Admin profile.",
                "missing_tables": missing,
                "missing_session_columns": missing_columns,
                "missing_approval_columns": missing_approval_columns,
            },
        )


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


def _assert_tenant_member(user: models.User, amo: models.AMO, *, allow_platform: bool = False) -> None:
    if allow_platform and getattr(user, "is_superuser", False):
        return
    if getattr(user, "is_superuser", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform superusers must use the platform support-session control plane.",
        )
    effective_amo_id = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if not tenant_member(user, amo.id):
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


def _approval_roles(db: Session, grant_id: str) -> set[str]:
    rows = db.execute(
        text("""
            SELECT DISTINCT approver_role
            FROM admin_access_grant_approvals
            WHERE grant_id = :grant_id
              AND decision = 'APPROVED'
              AND approver_role IS NOT NULL
        """),
        {"grant_id": grant_id},
    ).scalars().all()
    return {
        role_registry.canonical_role_key(value) or str(value or "").upper()
        for value in rows
    }


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


def _active_session(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    auth_session_id: str,
    implicit_admin: bool,
    now: datetime,
) -> dict[str, Any] | None:
    row = db.execute(
        text("""
            SELECT s.id, s.grant_id, s.activated_at, s.expires_at
            FROM admin_profile_sessions s
            LEFT JOIN admin_access_grants g ON g.id = s.grant_id
            WHERE s.amo_id = :amo_id
              AND s.user_id = :user_id
              AND s.auth_session_id = :auth_session_id
              AND s.revoked_at IS NULL
              AND s.expires_at > :now
              AND (
                (
                  :implicit_admin = TRUE
                  AND s.grant_id IS NULL
                )
                OR (
                  s.grant_id IS NOT NULL
                  AND g.amo_id = s.amo_id
                  AND g.user_id = s.user_id
                  AND g.status = 'ACTIVE'
                  AND (g.valid_from IS NULL OR g.valid_from <= :now)
                  AND (g.valid_until IS NULL OR g.valid_until > :now)
                )
              )
            ORDER BY s.activated_at DESC
            LIMIT 1
        """),
        {
            "amo_id": amo_id,
            "user_id": user_id,
            "auth_session_id": auth_session_id,
            "implicit_admin": implicit_admin,
            "now": now,
        },
    ).mappings().first()
    return dict(row) if row else None


def _state(db: Session, *, amo: models.AMO, user: models.User) -> dict[str, Any]:
    _ensure_schema(db)
    implicit = _is_implicit_admin(user)
    if implicit:
        return {
            "eligible": True,
            "active": True,
            "session_id": None,
            "expires_at": None,
            "grant_type": "PERMANENT",
            "reason": "Standing AMO administrator assigned by the platform superuser",
        }
    now = _utcnow()
    auth_session_id = _auth_session_id(user)
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
    db.execute(
        text("""
            UPDATE admin_access_grants
            SET status = 'EXPIRED', updated_at = :now
            WHERE amo_id = :amo_id
              AND status = 'ACTIVE'
              AND valid_until IS NOT NULL
              AND valid_until <= :now
        """),
        {"now": now, "amo_id": str(amo.id)},
    )
    grant = _eligible_grant(db, amo_id=str(amo.id), user_id=str(user.id), now=now)
    session = _active_session(
        db,
        amo_id=str(amo.id),
        user_id=str(user.id),
        auth_session_id=auth_session_id,
        implicit_admin=False,
        now=now,
    )
    eligible = grant is not None
    return {
        "eligible": eligible,
        "active": bool(session),
        "session_id": session.get("id") if session else None,
        "expires_at": session.get("expires_at") if session else None,
        "grant_type": grant.get("grant_type") if grant else None,
        "reason": grant.get("reason") if grant else None,
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
    if can_revoke_administrator(user, amo.id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the platform superuser or this tenant's Accountable Executive may approve requests or revoke administrator access.",
    )


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
    if _is_implicit_admin(current_user):
        # Standing authority is assigned by the platform superuser and is
        # already active. Do not create a misleading temporary session row.
        db.commit()
        return _state(db, amo=amo, user=current_user)
    now = _utcnow()
    auth_session_id = _auth_session_id(current_user)
    grant = _eligible_grant(db, amo_id=str(amo.id), user_id=str(current_user.id), now=now)
    if not grant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No approved administrator grant is active for this user.")

    db.execute(
        text("""
            UPDATE admin_profile_sessions
            SET revoked_at = :now
            WHERE amo_id = :amo_id
              AND user_id = :user_id
              AND auth_session_id = :auth_session_id
              AND revoked_at IS NULL
        """),
        {
            "now": now,
            "amo_id": str(amo.id),
            "user_id": str(current_user.id),
            "auth_session_id": auth_session_id,
        },
    )
    expires_at = now + timedelta(minutes=SESSION_DURATION_MINUTES)
    grant_valid_until = _as_utc(grant.get("valid_until")) if grant else None
    if grant_valid_until and grant_valid_until < expires_at:
        expires_at = grant_valid_until
    session_id = str(uuid4())
    db.execute(
        text("""
            INSERT INTO admin_profile_sessions (
                id, amo_id, user_id, auth_session_id, grant_id, activated_at,
                expires_at, revoked_at, created_at
            ) VALUES (
                :id, :amo_id, :user_id, :auth_session_id, :grant_id, :activated_at,
                :expires_at, NULL, :created_at
            )
        """),
        {
            "id": session_id,
            "amo_id": str(amo.id),
            "user_id": str(current_user.id),
            "auth_session_id": auth_session_id,
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
        detail=f"Authentication session {auth_session_id}",
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
    if _is_implicit_admin(current_user):
        # A user cannot deactivate a standing platform grant from inside the
        # tenant. The platform superuser must revoke the overlay explicitly.
        db.commit()
        return _state(db, amo=amo, user=current_user)
    now = _utcnow()
    auth_session_id = _auth_session_id(current_user)
    db.execute(
        text("""
            UPDATE admin_profile_sessions
            SET revoked_at = :now
            WHERE amo_id = :amo_id
              AND user_id = :user_id
              AND auth_session_id = :auth_session_id
              AND revoked_at IS NULL
        """),
        {
            "now": now,
            "amo_id": str(amo.id),
            "user_id": str(current_user.id),
            "auth_session_id": auth_session_id,
        },
    )
    _record_event(
        db,
        amo_id=str(amo.id),
        actor_user_id=str(current_user.id),
        subject_user_id=str(current_user.id),
        event_type="ADMIN_PROFILE_DEACTIVATED",
        detail=f"Authentication session {auth_session_id}",
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
    _assert_tenant_member(current_user, amo, allow_platform=True)
    _ensure_schema(db)
    may_view_all = is_tenant_admin(current_user) or can_revoke_administrator(current_user, amo.id)
    rows = db.execute(
        text("""
            SELECT g.*,
                   target.full_name AS user_name,
                   target.email AS user_email,
                   requester.full_name AS requested_by_name,
                   (
                       SELECT COUNT(DISTINCT a.approver_user_id)
                       FROM admin_access_grant_approvals a
                       WHERE a.grant_id = g.id AND a.decision = 'APPROVED'
                   ) AS approval_count,
                   EXISTS (
                       SELECT 1 FROM admin_access_grant_approvals a
                       WHERE a.grant_id = g.id
                         AND a.decision = 'APPROVED'
                         AND a.approver_role = 'ACCOUNTABLE_EXECUTIVE'
                   ) AS accountable_executive_approved,
                   EXISTS (
                       SELECT 1 FROM admin_access_grant_approvals a
                       WHERE a.grant_id = g.id
                         AND a.decision = 'APPROVED'
                         AND a.approver_role = 'QUALITY_MANAGER'
                   ) AS quality_manager_approved,
                   EXISTS (
                       SELECT 1 FROM admin_access_grant_approvals a
                       WHERE a.grant_id = g.id
                         AND a.approver_user_id = :current_user_id
                   ) AS current_user_decided
            FROM admin_access_grants g
            JOIN users target ON target.id = g.user_id AND target.amo_id = g.amo_id
            JOIN users requester ON requester.id = g.requested_by_user_id
            WHERE g.amo_id = :amo_id
              AND (:may_view_all = TRUE OR g.user_id = :current_user_id)
            ORDER BY g.created_at DESC
            LIMIT 500
        """),
        {"amo_id": str(amo.id), "current_user_id": str(current_user.id), "may_view_all": may_view_all},
    ).mappings().all()
    return {
        "items": [dict(row) for row in rows],
        "required_approver_roles": ["ACCOUNTABLE_EXECUTIVE"],
        "standing_administrators": [
            {"id": user.id, "full_name": user.full_name, "email": user.email}
            for user in db.query(models.User).filter(
                models.User.amo_id == amo.id,
                models.User.is_active.is_(True),
                models.User.is_superuser.is_(False),
                (models.User.is_amo_admin.is_(True)) | (models.User.role == models.AccountRole.AMO_ADMIN),
            ).all()
        ] if may_view_all else [],
    }


@router.get("/{amo_code}/grant-candidates")
def list_admin_grant_candidates(
    amo_code: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    amo = _resolve_amo(db, amo_code)
    _assert_tenant_member(current_user, amo, allow_platform=True)
    _ensure_schema(db)
    rows = db.execute(
        text("""
            SELECT u.id, u.full_name, u.email, u.position_title,
                   profile.display_name AS access_profile_name
            FROM users u
            LEFT JOIN auth_user_role_assignments assignment
              ON assignment.user_id = u.id
             AND assignment.amo_id = u.amo_id
             AND assignment.is_primary = TRUE
             AND assignment.valid_to IS NULL
            LEFT JOIN auth_role_definitions profile ON profile.id = assignment.role_id
            WHERE u.amo_id = :amo_id
              AND u.is_active = TRUE
              AND u.is_superuser = FALSE
              AND u.is_amo_admin = FALSE
              AND (:may_assign = TRUE OR u.id = :current_user_id)
              AND CAST(u.role AS VARCHAR) <> 'SUPERUSER'
              AND NOT EXISTS (
                  SELECT 1 FROM admin_access_grants g
                  WHERE g.amo_id = u.amo_id
                    AND g.user_id = u.id
                    AND g.status IN ('PENDING', 'ACTIVE')
                    AND (g.valid_until IS NULL OR g.valid_until > :now)
              )
            ORDER BY COALESCE(u.full_name, u.email), u.email
            LIMIT 1000
        """),
        {"amo_id": str(amo.id), "current_user_id": str(current_user.id), "may_assign": is_tenant_admin(current_user) or can_revoke_administrator(current_user, amo.id), "now": _utcnow()},
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
    _assert_tenant_member(current_user, amo, allow_platform=True)
    _ensure_schema(db)
    may_assign = is_tenant_admin(current_user) or can_revoke_administrator(current_user, amo.id)
    if not may_assign and str(payload.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You may request administrator access only for yourself.")
    target = (
        db.query(models.User)
        .filter(models.User.id == payload.user_id, models.User.amo_id == amo.id)
        .with_for_update()
        .first()
    )
    if not target or not target.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active tenant user was not found.")
    if (
        target.is_superuser
        or target.is_amo_admin
        or _normalise_role(target) in {"SUPERUSER", "AMO_ADMIN"}
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account is not eligible for a governed tenant-administrator grant.",
        )
    existing_grant = db.execute(
        text("""
            SELECT id FROM admin_access_grants
            WHERE amo_id = :amo_id AND user_id = :user_id
              AND status IN ('PENDING', 'ACTIVE')
              AND (valid_until IS NULL OR valid_until > :now)
            LIMIT 1
        """),
        {"amo_id": str(amo.id), "user_id": str(target.id), "now": _utcnow()},
    ).first()
    if existing_grant:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user already has a pending or active administrator grant.",
        )

    if current_user.is_superuser:
        payload.grant_type, payload.valid_from, payload.valid_until = "PERMANENT", None, None
    valid_from = _as_utc(payload.valid_from) or _utcnow()
    valid_until = _as_utc(payload.valid_until)
    if payload.grant_type == "TEMPORARY" and not valid_until:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Temporary administrator grants require an expiry time.",
        )
    if payload.grant_type == "PERMANENT" and valid_until is not None:
        raise HTTPException(status_code=422, detail="Permanent administrator grants cannot have an expiry time.")
    if valid_until and (valid_until <= valid_from or valid_until <= _utcnow()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Grant expiry must be later than its start time.",
        )

    now = _utcnow()
    grant_id = str(uuid4())
    grant_status = "ACTIVE" if may_assign and str(target.id) != str(current_user.id) else "PENDING"
    if current_user.is_superuser:
        # Platform appointments are standing and never expire.
        payload.grant_type = "PERMANENT"
        valid_from, valid_until = now, None
        target.is_amo_admin = True
        db.add(target)
    db.execute(
        text("""
            INSERT INTO admin_access_grants (
                id, amo_id, user_id, grant_type, valid_from, valid_until,
                status, reason, requested_by_user_id, activated_at,
                revoked_at, revoked_by_user_id, created_at, updated_at
            ) VALUES (
                :id, :amo_id, :user_id, :grant_type, :valid_from, :valid_until,
                :grant_status, :reason, :requested_by_user_id, :activated_at,
                NULL, NULL, :created_at, :updated_at
            )
        """),
        {
            "id": grant_id,
            "amo_id": str(amo.id),
            "user_id": str(target.id),
            "grant_type": payload.grant_type,
            "grant_status": grant_status,
            "activated_at": now if grant_status == "ACTIVE" else None,
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
        event_type="ADMIN_GRANT_ASSIGNED" if grant_status == "ACTIVE" else "ADMIN_GRANT_REQUESTED",
        detail=payload.reason.strip(),
    )
    db.commit()
    return {
        "id": grant_id,
        "status": grant_status,
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
    _assert_tenant_member(current_user, amo, allow_platform=True)
    _ensure_schema(db)
    _require_governance_approver(db, amo=amo, user=current_user)
    grant = db.execute(
        text("SELECT * FROM admin_access_grants WHERE id = :grant_id AND amo_id = :amo_id" + (" FOR UPDATE" if db.get_bind().dialect.name == "postgresql" else "")),
        {"grant_id": grant_id, "amo_id": str(amo.id)},
    ).mappings().first()
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Administrator grant request was not found.")
    if grant["status"] != "PENDING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This administrator grant is no longer awaiting approval.")
    expiry = _as_utc(grant.get("valid_until"))
    if expiry and expiry <= _utcnow():
        raise HTTPException(status_code=409, detail="This administrator request has expired.")
    if str(grant["user_id"]) == str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The grantee cannot approve their own administrator access.")

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
    approver_role = _normalise_role(current_user)
    role_decision = db.execute(
        text("""
            SELECT 1 FROM admin_access_grant_approvals
            WHERE grant_id = :grant_id
              AND decision = 'APPROVED'
              AND approver_role = :approver_role
        """),
        {"grant_id": grant_id, "approver_role": approver_role},
    ).first()
    if role_decision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The {role_registry.role_definition(approver_role).label} approval is already recorded.",
        )

    db.execute(
        text("""
            INSERT INTO admin_access_grant_approvals (
                id, grant_id, approver_user_id, approver_role,
                decision, comment, created_at
            ) VALUES (
                :id, :grant_id, :approver_user_id, :approver_role,
                'APPROVED', :comment, :created_at
            )
        """),
        {
            "id": str(uuid4()),
            "grant_id": grant_id,
            "approver_user_id": str(current_user.id),
            "approver_role": approver_role,
            "comment": payload.comment,
            "created_at": now,
        },
    )
    count = _approval_count(db, grant_id)
    approval_roles = _approval_roles(db, grant_id)
    next_status = (
        "ACTIVE"
        if approval_roles.intersection({"ACCOUNTABLE_EXECUTIVE", "SUPERUSER"})
        else "PENDING"
    )
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
        "accountable_executive_approved": "ACCOUNTABLE_EXECUTIVE" in approval_roles,
        "quality_manager_approved": "QUALITY_MANAGER" in approval_roles,
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
    _assert_tenant_member(current_user, amo, allow_platform=True)
    _ensure_schema(db)
    grant = db.execute(
        text("SELECT id, user_id, requested_by_user_id, status FROM admin_access_grants WHERE id = :grant_id AND amo_id = :amo_id" + (" FOR UPDATE" if db.get_bind().dialect.name == "postgresql" else "")),
        {"grant_id": grant_id, "amo_id": str(amo.id)},
    ).mappings().first()
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Administrator grant was not found.")
    is_requester_cancelling = (
        grant["status"] == "PENDING"
        and str(grant["requested_by_user_id"]) == str(current_user.id)
    )
    if not is_requester_cancelling:
        _require_governance_approver(db, amo=amo, user=current_user)

    appointer = db.get(models.User, grant["requested_by_user_id"])
    target = db.query(models.User).filter(
        models.User.id == grant["user_id"], models.User.amo_id == amo.id,
    ).first()
    if (grant["status"] == "ACTIVE" and appointer and appointer.is_superuser
            and target and _is_implicit_admin(target)):
        # Platform appointments have both a permanent grant and a standing flag.
        # Revoking the register entry must remove both sources of authority.
        remove_administrator(amo_code, str(target.id),
                             AdminRemovalDecision(comment=payload.comment), current_user, db)
        return {"id": grant_id, "status": "REVOKED"}

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
            WHERE grant_id = :grant_id AND revoked_at IS NULL
        """),
        {"now": now, "grant_id": grant_id},
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


@router.post("/{amo_code}/administrators/{user_id}/revoke")
def remove_administrator(
    amo_code: str,
    user_id: str,
    payload: AdminRemovalDecision,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    amo = _resolve_amo(db, amo_code)
    _assert_tenant_member(current_user, amo, allow_platform=True)
    _require_governance_approver(db, amo=amo, user=current_user)
    _ensure_schema(db)
    target = db.query(models.User).filter(
        models.User.id == user_id, models.User.amo_id == amo.id,
        models.User.is_superuser.is_(False),
    ).with_for_update().first()
    if target is None:
        raise HTTPException(status_code=404, detail="Tenant administrator was not found.")
    now = _utcnow()
    target.is_amo_admin = False
    if target.role == models.AccountRole.AMO_ADMIN:
        from . import access_control
        profile = access_control.primary_access_profile(db, user=target)
        target.role = role_registry.resolve_account_role(profile.base_role_key) if profile and profile.base_role_key not in {None, "AMO_ADMIN", "SUPERUSER"} else models.AccountRole.USER
    if payload.deactivate_account:
        target.is_active = False
        target.deactivated_at = now
        target.deactivated_reason = payload.comment or "Administrator deactivated by authorized governance actor"
    target.token_revoked_at = now
    db.add(target)
    db.execute(text("""
        UPDATE admin_access_grants SET status = 'REVOKED', revoked_at = :now,
            revoked_by_user_id = :actor, updated_at = :now
        WHERE amo_id = :amo_id AND user_id = :user_id AND status IN ('PENDING', 'ACTIVE')
    """), {"amo_id": str(amo.id), "user_id": user_id, "now": now, "actor": str(current_user.id)})
    db.execute(text("""
        UPDATE admin_profile_sessions SET revoked_at = :now
        WHERE amo_id = :amo_id AND user_id = :user_id AND revoked_at IS NULL
    """), {"amo_id": str(amo.id), "user_id": user_id, "now": now})
    _record_event(db, amo_id=str(amo.id), actor_user_id=str(current_user.id),
                  subject_user_id=user_id, event_type="ADMINISTRATOR_REMOVED", detail=payload.comment)
    db.commit()
    return {"id": user_id, "status": "REVOKED", "account_active": target.is_active}
