# backend/amodb/apps/rostering/common.py
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from ..audit import services as audit_services
from ..foundations import models as foundation_models
from ..notifications import service as notification_service
from ..workforce import permissions as workforce_permissions
from . import models, schemas

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def effective_amo_id(user: account_models.User) -> str:
    return getattr(user, "effective_amo_id", None) or user.amo_id


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def model_fields_set(payload: Any) -> set[str]:
    return set(getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set())))


def dump(payload: Any, *, exclude_unset: bool = False) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=exclude_unset)
    return payload.dict(exclude_unset=exclude_unset)


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
    entity_type: str,
    entity_id: str,
    action: str,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
    critical: bool = False,
) -> None:
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
        metadata={"module": "rostering", **(metadata or {})},
        critical=critical,
    )


def notify_email(
    db: Session,
    *,
    amo_id: str,
    recipient: Optional[str],
    template_key: str,
    subject: str,
    context: dict[str, Any],
    correlation_id: str,
) -> None:
    try:
        notification_service.send_email(
            template_key=template_key,
            recipient=recipient,
            subject=subject,
            context=context,
            correlation_id=correlation_id,
            critical=False,
            amo_id=amo_id,
            db=db,
        )
    except Exception:
        return


def require_user(db: Session, *, amo_id: str, user_id: str, active_only: bool = True) -> account_models.User:
    query = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.id == user_id)
    if active_only:
        query = query.filter(account_models.User.is_active.is_(True))
    row = query.first()
    if not row:
        raise ValueError("User not found in AMO scope")
    if getattr(row, "is_system_account", False):
        raise ValueError("System accounts cannot be rostered")
    return row


def require_base(db: Session, *, amo_id: str, base_station_id: Optional[str]) -> Optional[foundation_models.BaseStation]:
    if not base_station_id:
        return None
    row = db.query(foundation_models.BaseStation).filter(
        foundation_models.BaseStation.amo_id == amo_id,
        foundation_models.BaseStation.id == base_station_id,
    ).first()
    if not row:
        raise ValueError("Base station not found in AMO scope")
    return row


def require_department(db: Session, *, amo_id: str, department_id: Optional[str]) -> Optional[account_models.Department]:
    if not department_id:
        return None
    row = db.query(account_models.Department).filter(
        account_models.Department.amo_id == amo_id,
        account_models.Department.id == department_id,
    ).first()
    if not row:
        raise ValueError("Department not found in AMO scope")
    return row


def require_shift_template(db: Session, *, amo_id: str, shift_template_id: Optional[str]) -> Optional[models.ShiftTemplate]:
    if not shift_template_id:
        return None
    row = db.query(models.ShiftTemplate).filter(models.ShiftTemplate.amo_id == amo_id, models.ShiftTemplate.id == shift_template_id).first()
    if not row:
        raise ValueError("Shift template not found in AMO scope")
    return row


def get_period(db: Session, *, amo_id: str, period_id: str) -> Optional[models.RosterPeriod]:
    return db.query(models.RosterPeriod).options(
        selectinload(models.RosterPeriod.versions)
        .selectinload(models.RosterVersion.assignments),
        selectinload(models.RosterPeriod.versions)
        .selectinload(models.RosterVersion.validation_findings),
    ).filter(models.RosterPeriod.amo_id == amo_id, models.RosterPeriod.id == period_id).first()


def get_version(db: Session, *, amo_id: str, version_id: str, lock: bool = False) -> Optional[models.RosterVersion]:
    query = db.query(models.RosterVersion).options(
        selectinload(models.RosterVersion.assignments).selectinload(models.RosterAssignment.user),
        selectinload(models.RosterVersion.assignments).selectinload(models.RosterAssignment.department),
        selectinload(models.RosterVersion.assignments).selectinload(models.RosterAssignment.base_station),
        selectinload(models.RosterVersion.assignments).selectinload(models.RosterAssignment.shift_template),
        selectinload(models.RosterVersion.assignments).selectinload(models.RosterAssignment.task_links),
        selectinload(models.RosterVersion.validation_findings),
        selectinload(models.RosterVersion.exceptions),
        selectinload(models.RosterVersion.period),
    ).filter(models.RosterVersion.amo_id == amo_id, models.RosterVersion.id == version_id)
    if lock:
        query = query.with_for_update()
    return query.first()


def get_assignment(db: Session, *, amo_id: str, assignment_id: str, include_deleted: bool = False, lock: bool = False) -> Optional[models.RosterAssignment]:
    query = db.query(models.RosterAssignment).options(
        selectinload(models.RosterAssignment.user),
        selectinload(models.RosterAssignment.department),
        selectinload(models.RosterAssignment.base_station),
        selectinload(models.RosterAssignment.shift_template),
        selectinload(models.RosterAssignment.task_links),
        selectinload(models.RosterAssignment.version),
    ).filter(models.RosterAssignment.amo_id == amo_id, models.RosterAssignment.id == assignment_id)
    if not include_deleted:
        query = query.filter(models.RosterAssignment.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    return query.first()


def ensure_draft(version: models.RosterVersion) -> None:
    if version.status != models.RosterVersionStatus.DRAFT:
        raise ValueError("Only draft roster versions can be edited")


def check_version_revision(version: models.RosterVersion, expected: Optional[int]) -> None:
    if expected is not None and version.state_revision != expected:
        raise RuntimeError(f"ROSTER_VERSION_REVISION_CONFLICT:{version.state_revision}")


def check_assignment_revision(assignment: models.RosterAssignment, expected: Optional[int]) -> None:
    if expected is not None and assignment.state_revision != expected:
        raise RuntimeError(f"ROSTER_ASSIGNMENT_REVISION_CONFLICT:{assignment.state_revision}")


def bump_version(version: models.RosterVersion) -> None:
    version.state_revision = int(version.state_revision or 1) + 1
    version.validation_fingerprint = None
    version.last_validated_at = None


def command_receipt(
    db: Session,
    *,
    amo_id: str,
    idempotency_key: str,
    operation: str,
    request_hash: str,
) -> Optional[models.RosterCommandReceipt]:
    row = db.query(models.RosterCommandReceipt).filter(
        models.RosterCommandReceipt.amo_id == amo_id,
        models.RosterCommandReceipt.idempotency_key == idempotency_key,
    ).first()
    if row and (row.operation != operation or row.request_hash != request_hash):
        raise ValueError("Idempotency key was already used for a different roster command")
    return row


def save_command_receipt(
    db: Session,
    *,
    amo_id: str,
    idempotency_key: str,
    operation: str,
    actor_user_id: str,
    request_hash: str,
    response_json: dict[str, Any],
) -> models.RosterCommandReceipt:
    row = models.RosterCommandReceipt(
        amo_id=amo_id,
        idempotency_key=idempotency_key,
        operation=operation,
        actor_user_id=actor_user_id,
        request_hash=request_hash,
        response_json=response_json,
    )
    db.add(row)
    db.flush()
    return row


def assignment_hours(row: models.RosterAssignment) -> float:
    if row.planned_minutes is not None:
        return max(float(row.planned_minutes) / 60.0, 0.0)
    return max((row.ends_at - row.starts_at).total_seconds() / 3600.0, 0.0)


def task_link_hours(row: models.RosterTaskAssignmentLink) -> float:
    if row.allocated_hours is not None:
        return max(float(row.allocated_hours), 0.0)
    if row.allocated_start and row.allocated_end:
        return max((row.allocated_end - row.allocated_start).total_seconds() / 3600.0, 0.0)
    if row.task_assignment and row.task_assignment.allocated_hours is not None:
        return max(float(row.task_assignment.allocated_hours), 0.0)
    return 0.0


def serialize_assignment(row: models.RosterAssignment) -> schemas.RosterAssignmentRead:
    links = list(row.task_links or [])
    return schemas.RosterAssignmentRead(
        id=row.id,
        amo_id=row.amo_id,
        version_id=row.version_id,
        user_id=row.user_id,
        department_id=row.department_id,
        base_station_id=row.base_station_id,
        shift_template_id=row.shift_template_id,
        status=row.status,
        source=row.source,
        source_reference_id=row.source_reference_id,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        planned_minutes=row.planned_minutes,
        role_label=row.role_label,
        team_code=row.team_code,
        location_label=row.location_label,
        task_note=row.task_note,
        change_reason=row.change_reason,
        locked_after_publish=row.locked_after_publish,
        state_revision=row.state_revision,
        deleted_at=row.deleted_at,
        created_by_user_id=row.created_by_user_id,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        user_full_name=getattr(row.user, "full_name", None),
        user_staff_code=getattr(row.user, "staff_code", None),
        user_role=enum_value(getattr(row.user, "role", "")) if row.user else None,
        department_code=getattr(row.department, "code", None),
        department_name=getattr(row.department, "name", None),
        base_code=getattr(row.base_station, "code", None),
        base_name=getattr(row.base_station, "name", None),
        shift_code=getattr(row.shift_template, "code", None),
        shift_label=getattr(row.shift_template, "label", None),
        shift_kind=enum_value(getattr(row.shift_template, "kind", "")) if row.shift_template else None,
        linked_task_count=len(links),
        linked_task_hours=round(sum(task_link_hours(link) for link in links), 2),
    )


def serialize_finding(row: models.RosterValidationFinding) -> schemas.RosterValidationFindingRead:
    return schemas.RosterValidationFindingRead.model_validate(row)


def serialize_version(
    row: models.RosterVersion,
    *,
    current_user: Optional[account_models.User] = None,
    db: Optional[Session] = None,
) -> schemas.RosterVersionRead:
    findings = list(row.validation_findings or [])
    blockers = sum(1 for item in findings if item.severity == models.RosterValidationSeverity.BLOCKER and not item.resolved)
    warnings = sum(1 for item in findings if item.severity == models.RosterValidationSeverity.WARNING and not item.resolved)
    overridden = sum(1 for item in findings if item.resolved and item.overridden_at is not None)
    permissions = set()
    approval_required = approval_approved = approval_pending = 0
    scoped_can_approve = False
    scoped_can_publish = False
    if current_user is not None and db is not None:
        permissions = set(workforce_permissions.permissions_for_user(db, user=current_user))
        from . import governance
        approvals = governance.approval_rows(db, version_id=row.id)
        approval_required = len(approvals)
        approval_approved = sum(item.status == models.RosterDepartmentApprovalStatus.APPROVED for item in approvals)
        approval_pending = sum(item.status != models.RosterDepartmentApprovalStatus.APPROVED for item in approvals)
        scoped_can_approve = any(
            item.status != models.RosterDepartmentApprovalStatus.APPROVED
            and governance.can_approve_scope(db, user=current_user, department_id=item.department_id, base_station_id=item.base_station_id)
            for item in approvals
        )
        scoped_can_publish = bool(approvals) and all(
            item.status == models.RosterDepartmentApprovalStatus.APPROVED
            and governance.can_publish_scope(db, user=current_user, department_id=item.department_id, base_station_id=item.base_station_id)
            for item in approvals
        )
    return schemas.RosterVersionRead(
        id=row.id,
        amo_id=row.amo_id,
        period_id=row.period_id,
        source_version_id=row.source_version_id,
        version_no=row.version_no,
        status=row.status,
        title=row.title,
        change_summary=row.change_summary,
        amendment_type=row.amendment_type,
        amendment_reason=row.amendment_reason,
        effective_from=row.effective_from,
        idempotency_key=row.idempotency_key,
        state_revision=row.state_revision,
        last_validated_at=row.last_validated_at,
        validation_fingerprint=row.validation_fingerprint,
        created_by_user_id=row.created_by_user_id,
        submitted_by_user_id=row.submitted_by_user_id,
        approved_by_user_id=row.approved_by_user_id,
        published_by_user_id=row.published_by_user_id,
        submitted_at=row.submitted_at,
        approved_at=row.approved_at,
        published_at=row.published_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        assignments_count=sum(1 for item in row.assignments or [] if item.deleted_at is None),
        blocker_count=blockers,
        warning_count=warnings,
        overridden_count=overridden,
        acknowledgement_count=0,
        approval_required_count=approval_required,
        approval_approved_count=approval_approved,
        approval_pending_count=approval_pending,
        can_edit=row.status == models.RosterVersionStatus.DRAFT and workforce_permissions.PermissionCode.ROSTER_EDIT.value in permissions,
        can_submit=row.status == models.RosterVersionStatus.DRAFT and blockers == 0 and workforce_permissions.PermissionCode.ROSTER_SUBMIT.value in permissions,
        can_approve=row.status == models.RosterVersionStatus.SUBMITTED and scoped_can_approve,
        can_publish=row.status == models.RosterVersionStatus.APPROVED and blockers == 0 and scoped_can_publish,
    )


def serialize_period(row: models.RosterPeriod, *, current_user: Optional[account_models.User] = None, db: Optional[Session] = None) -> schemas.RosterPeriodRead:
    return schemas.RosterPeriodRead(
        id=row.id,
        amo_id=row.amo_id,
        period_code=row.period_code,
        name=row.name,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        status=row.status,
        notes=row.notes,
        timezone_name=row.timezone_name,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        versions=[serialize_version(version, current_user=current_user, db=db) for version in sorted(row.versions or [], key=lambda item: item.version_no, reverse=True)],
    )


def can_view_roster(db: Session, *, user: account_models.User) -> bool:
    return workforce_permissions.any_permission(
        db,
        user=user,
        permissions=[
            workforce_permissions.PermissionCode.ROSTER_VIEW_OWN,
            workforce_permissions.PermissionCode.ROSTER_VIEW_DEPARTMENT,
            workforce_permissions.PermissionCode.ROSTER_VIEW_ALL,
        ],
    )


def can_manage_roster(db: Session, *, user: account_models.User) -> bool:
    return workforce_permissions.has_permission(db, user=user, permission=workforce_permissions.PermissionCode.ROSTER_EDIT)


def can_approve_roster(db: Session, *, user: account_models.User) -> bool:
    return workforce_permissions.has_permission(db, user=user, permission=workforce_permissions.PermissionCode.ROSTER_APPROVE)
