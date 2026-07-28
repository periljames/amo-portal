"""Rostering setup-readiness and controlled automation endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import permissions as workforce_permissions
from . import automation_schemas, automation_service, services
from .automation_models import (
    RosterAutomationRunStatus,
    RosterAutomationTrigger,
    RosterGenerationRun,
)

router = APIRouter(prefix="/rostering", tags=["rostering-automation"])


def _amo(user: account_models.User) -> str:
    return services.effective_amo_id(user)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _error(
    detail: str,
    *,
    code: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    conflicts: list[dict] | None = None,
    retryable: bool = False,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "detail": detail,
            "error_code": code,
            "field_errors": {},
            "conflicts": conflicts or [],
            "retryable": retryable,
        },
    )


def _require(db: Session, user: account_models.User, permission: workforce_permissions.PermissionCode) -> None:
    workforce_permissions.require_permission(db, user=user, permission=permission)


def _record_failed_run(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: automation_schemas.RosterAutomationRunRequest,
    message: str,
) -> bool:
    """Roll back all work, then retain failure evidence in a new transaction.

    The period, draft, assignment and validation work performed by an automation
    attempt is one atomic unit. A failure must never commit a partially generated
    roster merely to preserve the failure record. This helper first rolls back
    that entire unit, then records the failed attempt separately.
    """
    db.rollback()
    try:
        existing = db.query(RosterGenerationRun).filter(
            RosterGenerationRun.amo_id == amo_id,
            RosterGenerationRun.idempotency_key == payload.idempotency_key,
        ).first()
        if existing is not None:
            return str(getattr(existing.status, "value", existing.status)) == RosterAutomationRunStatus.FAILED.value

        policy = automation_service.get_or_create_policy(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
        )
        if payload.target_from and payload.target_to:
            target_from, target_to = payload.target_from, payload.target_to
        else:
            target_from, target_to = automation_service._target_window(policy)

        now = _utcnow()
        row = RosterGenerationRun(
            amo_id=amo_id,
            policy_id=policy.id,
            trigger=RosterAutomationTrigger.MANUAL,
            status=RosterAutomationRunStatus.FAILED,
            idempotency_key=payload.idempotency_key,
            dry_run=False,
            target_from=target_from.isoformat(),
            target_to=target_to.isoformat(),
            generated_count=0,
            skipped_count=0,
            conflict_count=0,
            validation_blocker_count=0,
            validation_warning_count=0,
            summary_json={
                "operational_changes_committed": False,
                "failure_recorded_after_rollback": True,
            },
            error_message=message,
            requested_by_user_id=actor_user_id,
            started_at=now,
            completed_at=now,
            created_at=now,
        )
        db.add(row)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


@router.get("/setup/readiness", response_model=automation_schemas.RosterSetupReadinessResponse)
def roster_setup_readiness(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT)
    result = automation_service.readiness(
        db,
        amo_id=_amo(current_user),
        actor_user_id=current_user.id,
    )
    db.commit()
    return result


@router.get("/automation-policy", response_model=automation_schemas.RosterGenerationPolicyRead)
def get_roster_automation_policy(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT)
    row = automation_service.get_or_create_policy(
        db,
        amo_id=_amo(current_user),
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return row


@router.patch("/automation-policy", response_model=automation_schemas.RosterGenerationPolicyRead)
def patch_roster_automation_policy(
    payload: automation_schemas.RosterGenerationPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_PATTERNS)
    row = automation_service.get_or_create_policy(
        db,
        amo_id=_amo(current_user),
        actor_user_id=current_user.id,
    )
    try:
        automation_service.update_policy(
            db,
            row=row,
            actor_user_id=current_user.id,
            payload=payload,
        )
        db.commit()
        db.refresh(row)
        return row
    except RuntimeError as exc:
        db.rollback()
        message = str(exc)
        if message.startswith("ROSTER_AUTOMATION_REVISION_CONFLICT:"):
            current = int(message.rsplit(":", 1)[-1])
            raise _error(
                "Roster automation settings changed since they were loaded. Refresh and retry.",
                code="ROSTER_AUTOMATION_REVISION_CONFLICT",
                status_code=status.HTTP_409_CONFLICT,
                conflicts=[{"current_state_revision": current}],
                retryable=True,
            ) from exc
        raise
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise _error(str(exc), code="ROSTER_AUTOMATION_POLICY_INVALID") from exc


@router.post("/automation/preview", response_model=automation_schemas.RosterAutomationPreviewResponse)
def preview_roster_automation(
    payload: automation_schemas.RosterAutomationPreviewRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_PATTERNS)
    try:
        result = automation_service.preview(
            db,
            amo_id=_amo(current_user),
            actor_user_id=current_user.id,
            payload=payload,
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="ROSTER_AUTOMATION_PREVIEW_INVALID") from exc


@router.post("/automation/run", response_model=automation_schemas.RosterGenerationRunRead)
def run_roster_automation(
    payload: automation_schemas.RosterAutomationRunRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_CREATE)
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_PATTERNS)
    amo_id = _amo(current_user)
    try:
        row = automation_service.run(
            db,
            amo_id=amo_id,
            actor_user_id=current_user.id,
            payload=payload,
        )
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError as exc:
        db.rollback()
        raise _error(str(exc), code="ROSTER_AUTOMATION_DATABASE_CONFLICT", status_code=409) from exc
    except (ValueError, RuntimeError) as exc:
        message = str(exc)
        evidence_retained = _record_failed_run(
            db,
            amo_id=amo_id,
            actor_user_id=current_user.id,
            payload=payload,
            message=message,
        )
        raise _error(
            message,
            code="ROSTER_AUTOMATION_RUN_FAILED",
            conflicts=[{"failure_evidence_retained": evidence_retained}],
        ) from exc


@router.get("/automation/runs", response_model=list[automation_schemas.RosterGenerationRunRead])
def list_roster_automation_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT)
    return automation_service.list_runs(db, amo_id=_amo(current_user), limit=limit)
