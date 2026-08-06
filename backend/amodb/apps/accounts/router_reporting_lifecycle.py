"""Assignment lifecycle APIs for reporting-line administration.

Creating a hierarchy is only part of the operational workflow. These endpoints
support correcting manager mappings, revising display titles, scheduling an end
and transferring a person without deleting history or granting new portal or
aviation authority.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_db
from amodb.security import get_current_active_user, require_admin

from . import corporate_structure_models as org_models
from . import models
from . import reporting_lifecycle_schemas as lifecycle_schemas
from . import reporting_line_models as line_models
from . import reporting_line_schemas as line_schemas
from . import router_reporting_lines as reporting
from .router_admin import router as admin_router

portal_router = APIRouter(
    prefix="/organization/reporting/manager",
    tags=["organization_reporting_lifecycle"],
)


def _assignment_context(
    db: Session,
    actor: models.User,
    assignment_id: str,
    *,
    manager_mode: bool,
) -> tuple[str, org_models.PositionAssignment, org_models.OrganizationPosition, models.User]:
    amo_id = reporting._amo_id(actor)
    assignment = (
        db.query(org_models.PositionAssignment)
        .filter(
            org_models.PositionAssignment.id == assignment_id,
            org_models.PositionAssignment.amo_id == amo_id,
        )
        .with_for_update()
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Position assignment not found.")
    position = reporting._position_or_404(db, amo_id, str(assignment.position_id))
    user = reporting._tenant_user(db, amo_id, str(assignment.user_id), active=False)
    if manager_mode:
        scope = reporting._manageable_unit_ids(db, amo_id, actor)
        if str(position.unit_id) not in scope:
            raise HTTPException(status_code=403, detail="This assignment is outside your management scope.")
        if position.is_regulatory_post or position.authority_acceptance_required:
            raise HTTPException(
                status_code=403,
                detail="Regulatory and authority-accepted assignments require tenant-administrator control.",
            )
    return amo_id, assignment, position, user


def _require_open_assignment(assignment: org_models.PositionAssignment) -> None:
    if str(assignment.status or "").upper() not in reporting.ACTIVE_ASSIGNMENT_STATUSES:
        raise HTTPException(status_code=409, detail="Only an active assignment can be changed or transferred.")


def _reset_display_title(
    db: Session,
    assignment: org_models.PositionAssignment,
    position: org_models.OrganizationPosition,
    user: models.User,
) -> None:
    now = datetime.now(timezone.utc)
    rows = (
        db.query(line_models.PersonnelTitlePreference)
        .filter(
            line_models.PersonnelTitlePreference.assignment_id == assignment.id,
            line_models.PersonnelTitlePreference.status.in_(["PENDING", "APPROVED"]),
        )
        .all()
    )
    for row in rows:
        row.status = "WITHDRAWN" if row.status == "PENDING" else "SUPERSEDED"
        row.decided_at = now
        db.add(row)
    if assignment.is_primary:
        user.position_title = position.title
        db.add(user)


def _apply_display_title(
    db: Session,
    *,
    amo_id: str,
    actor: models.User,
    assignment: org_models.PositionAssignment,
    position: org_models.OrganizationPosition,
    user: models.User,
    display_title: Optional[str],
    manager_mode: bool,
) -> None:
    if display_title is None:
        return
    title = display_title.strip()
    if title.casefold() == position.title.casefold():
        _reset_display_title(db, assignment, position, user)
        return
    reporting._create_approved_preference(
        db,
        amo_id=amo_id,
        user=user,
        assignment=assignment,
        title=title,
        actor=actor,
        source="MANAGER_SET" if manager_mode else "ADMIN_SET",
    )


def _update_assignment(
    db: Session,
    actor: models.User,
    assignment_id: str,
    payload: lifecycle_schemas.ReportingAssignmentUpdate,
    *,
    manager_mode: bool,
):
    amo_id, assignment, position, user = _assignment_context(
        db,
        actor,
        assignment_id,
        manager_mode=manager_mode,
    )
    _require_open_assignment(assignment)
    changes = payload.model_dump(exclude_unset=True)
    display_title = changes.pop("display_title", None) if "display_title" in changes else None

    if "assignment_type" in changes:
        assignment_type = str(changes["assignment_type"] or "").strip().upper()
        if assignment_type not in reporting.ALLOWED_ASSIGNMENT_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported assignment type.")
        changes["assignment_type"] = assignment_type

    if "effective_to" in changes:
        reporting._date_order(assignment.effective_from, changes["effective_to"], "Assignment")

    matrix_reporting = bool(changes.get("matrix_reporting", assignment.matrix_reporting))
    matrix_reason = changes.get("matrix_reason", assignment.matrix_reason)
    if matrix_reporting and not str(matrix_reason or "").strip():
        raise HTTPException(status_code=422, detail="A reason is required for matrix reporting.")

    manager_fields_changed = any(
        key in changes
        for key in ("reporting_manager_user_id", "matrix_reporting", "matrix_reason")
    )
    if manager_fields_changed:
        requested_manager = changes.get(
            "reporting_manager_user_id",
            assignment.reporting_manager_user_id,
        )
        manager = reporting._resolve_manager(
            db,
            amo_id,
            position,
            str(requested_manager) if requested_manager else None,
            matrix_reporting=matrix_reporting,
            matrix_reason=matrix_reason,
        )
        reporting._assert_manager_cycle(
            db,
            amo_id,
            str(user.id),
            str(manager.id) if manager else None,
        )
        changes["reporting_manager_user_id"] = manager.id if manager else None

    before = {
        key: getattr(assignment, key)
        for key in changes
        if hasattr(assignment, key)
    }
    for key, value in changes.items():
        if hasattr(assignment, key):
            setattr(assignment, key, value)
    if assignment.effective_to and assignment.effective_to <= date.today():
        assignment.status = "ENDED"
    db.add(assignment)
    _apply_display_title(
        db,
        amo_id=amo_id,
        actor=actor,
        assignment=assignment,
        position=position,
        user=user,
        display_title=display_title,
        manager_mode=manager_mode,
    )
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        entity_type="accounts.position_assignment",
        entity_id=str(assignment.id),
        action="REPORTING_ASSIGNMENT_UPDATED",
        before=before,
        after={
            **{key: str(value) if value is not None else None for key, value in changes.items()},
            "display_title": display_title,
            "authorization_changed": False,
        },
        metadata={"module": "accounts", "source": "reporting_assignment_lifecycle"},
    )
    db.commit()
    return reporting._workspace(db, actor)


def _end_assignment(
    db: Session,
    actor: models.User,
    assignment_id: str,
    payload: lifecycle_schemas.ReportingAssignmentEnd,
    *,
    manager_mode: bool,
):
    amo_id, assignment, position, user = _assignment_context(
        db,
        actor,
        assignment_id,
        manager_mode=manager_mode,
    )
    _require_open_assignment(assignment)
    reporting._date_order(assignment.effective_from, payload.end_on, "Assignment")
    before = {
        "effective_to": str(assignment.effective_to) if assignment.effective_to else None,
        "status": assignment.status,
    }
    assignment.effective_to = payload.end_on
    if payload.end_on <= date.today():
        assignment.status = "ENDED"
        _reset_display_title(db, assignment, position, user)
    db.add(assignment)
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        entity_type="accounts.position_assignment",
        entity_id=str(assignment.id),
        action="REPORTING_ASSIGNMENT_END_SCHEDULED" if payload.end_on > date.today() else "REPORTING_ASSIGNMENT_ENDED",
        before=before,
        after={
            "effective_to": str(payload.end_on),
            "status": assignment.status,
            "reason": payload.reason,
            "authorization_changed": False,
        },
        metadata={"module": "accounts", "source": "reporting_assignment_lifecycle"},
    )
    db.commit()
    return reporting._workspace(db, actor)


def _transfer_assignment(
    db: Session,
    actor: models.User,
    assignment_id: str,
    payload: lifecycle_schemas.ReportingAssignmentTransfer,
    *,
    manager_mode: bool,
):
    amo_id, assignment, _position, user = _assignment_context(
        db,
        actor,
        assignment_id,
        manager_mode=manager_mode,
    )
    _require_open_assignment(assignment)
    if payload.effective_from <= assignment.effective_from:
        raise HTTPException(
            status_code=422,
            detail="Transfer date must be after the current assignment start date.",
        )
    previous_end = payload.effective_from - timedelta(days=1)
    assignment.effective_to = previous_end
    if previous_end <= date.today():
        assignment.status = "ENDED"
    db.add(assignment)

    create_payload = line_schemas.GuidedAssignmentCreate(
        user_id=str(user.id),
        position_id=payload.target_position_id,
        reporting_manager_user_id=payload.reporting_manager_user_id,
        assignment_type=payload.assignment_type,
        is_primary=bool(assignment.is_primary),
        effective_from=payload.effective_from,
        effective_to=None,
        fte_percent=Decimal(str(payload.fte_percent)),
        matrix_reporting=payload.matrix_reporting,
        matrix_reason=payload.matrix_reason,
        display_title=payload.display_title,
        appointment_reference=payload.appointment_reference,
        authority_acceptance_reference=payload.authority_acceptance_reference,
        authority_accepted_on=payload.authority_accepted_on,
        delegation_limitations=payload.delegation_limitations,
    )
    replacement = reporting._create_assignment(
        db,
        actor,
        create_payload,
        manager_mode=manager_mode,
    )
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        entity_type="accounts.position_assignment",
        entity_id=str(assignment.id),
        action="REPORTING_ASSIGNMENT_TRANSFERRED",
        before={"position_id": str(assignment.position_id)},
        after={
            "effective_to": str(previous_end),
            "replacement_assignment_id": str(replacement.id),
            "replacement_position_id": payload.target_position_id,
            "reason": payload.reason,
            "authorization_changed": False,
        },
        metadata={"module": "accounts", "source": "reporting_assignment_lifecycle"},
    )
    db.commit()
    return reporting._workspace(db, actor)


@portal_router.patch("/assignments/{assignment_id}", response_model=line_schemas.ReportingWorkspaceRead)
def manager_update_assignment(
    assignment_id: str,
    payload: lifecycle_schemas.ReportingAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    reporting._manager_scope(db, current_user)
    return _update_assignment(db, current_user, assignment_id, payload, manager_mode=True)


@portal_router.post("/assignments/{assignment_id}/end", response_model=line_schemas.ReportingWorkspaceRead)
def manager_end_assignment(
    assignment_id: str,
    payload: lifecycle_schemas.ReportingAssignmentEnd,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    reporting._manager_scope(db, current_user)
    return _end_assignment(db, current_user, assignment_id, payload, manager_mode=True)


@portal_router.post("/assignments/{assignment_id}/transfer", response_model=line_schemas.ReportingWorkspaceRead)
def manager_transfer_assignment(
    assignment_id: str,
    payload: lifecycle_schemas.ReportingAssignmentTransfer,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    reporting._manager_scope(db, current_user)
    return _transfer_assignment(db, current_user, assignment_id, payload, manager_mode=True)


@admin_router.patch("/organization/reporting/assignments/{assignment_id}", response_model=line_schemas.ReportingWorkspaceRead)
def admin_update_reporting_assignment(
    assignment_id: str,
    payload: lifecycle_schemas.ReportingAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    return _update_assignment(db, current_user, assignment_id, payload, manager_mode=False)


@admin_router.post("/organization/reporting/assignments/{assignment_id}/end", response_model=line_schemas.ReportingWorkspaceRead)
def admin_end_reporting_assignment(
    assignment_id: str,
    payload: lifecycle_schemas.ReportingAssignmentEnd,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    return _end_assignment(db, current_user, assignment_id, payload, manager_mode=False)


@admin_router.post("/organization/reporting/assignments/{assignment_id}/transfer", response_model=line_schemas.ReportingWorkspaceRead)
def admin_transfer_reporting_assignment(
    assignment_id: str,
    payload: lifecycle_schemas.ReportingAssignmentTransfer,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    return _transfer_assignment(db, current_user, assignment_id, payload, manager_mode=False)
