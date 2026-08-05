"""Guided reporting-line setup with non-authoritative display titles.

The endpoints in this module deliberately keep four controls separate:

* the canonical corporate position and its reporting-position parent;
* the person occupying that position and their actual reporting manager;
* the title shown in the user interface; and
* portal permissions, licences, competence and maintenance authorisations.

Changing a reporting line or display title never grants a role, capability,
group membership, licence privilege or certification authority.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_db
from amodb.security import get_current_active_user, require_admin

from . import corporate_structure_models as org_models
from . import models
from . import reporting_line_models as line_models
from . import reporting_line_schemas as line_schemas
from .router_admin import router as admin_router

portal_router = APIRouter(prefix="/organization/reporting", tags=["organization_reporting"])

ACTIVE_ASSIGNMENT_STATUSES = {"ACTIVE", "ACTING", "APPROVED"}
ALLOWED_ASSIGNMENT_TYPES = {
    "SUBSTANTIVE",
    "ACTING",
    "SECONDMENT",
    "TEMPORARY",
    "INTERIM",
    "INTERNSHIP",
    "APPRENTICESHIP",
    "CONTRACT",
}
AUTHORIZATION_BOUNDARY = (
    "Display titles and reporting lines are organization metadata only. Portal access, "
    "segregation-of-duties controls, licences, competence findings and maintenance "
    "authorisations continue to use governed roles, capabilities, groups, credentials "
    "and authorisation records."
)


def _role_value(user: models.User) -> str:
    return str(getattr(getattr(user, "role", None), "value", getattr(user, "role", "")) or "").upper()


def _is_admin_actor(user: models.User) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_amo_admin", False)
        or _role_value(user) in {"AMO_ADMIN", "QUALITY_MANAGER", "SAFETY_MANAGER"}
    )


def _amo_id(user: models.User) -> str:
    value = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if not value:
        raise HTTPException(status_code=403, detail="A tenant context is required.")
    return str(value)


def _active_assignment_filter(amo_id: str, active_on: Optional[date] = None):
    active_on = active_on or date.today()
    return (
        org_models.PositionAssignment.amo_id == amo_id,
        org_models.PositionAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        org_models.PositionAssignment.effective_from <= active_on,
        or_(
            org_models.PositionAssignment.effective_to.is_(None),
            org_models.PositionAssignment.effective_to >= active_on,
        ),
    )


def _date_order(start: date, end: Optional[date], label: str) -> None:
    if end and end < start:
        raise HTTPException(status_code=422, detail=f"{label} end date cannot be before its start date.")


def _normalise_code(value: str) -> str:
    return "_".join(value.strip().upper().replace("-", " ").split())


def _all_units(db: Session, amo_id: str) -> list[org_models.OrganizationUnit]:
    return (
        db.query(org_models.OrganizationUnit)
        .filter(org_models.OrganizationUnit.amo_id == amo_id)
        .order_by(org_models.OrganizationUnit.sort_order, org_models.OrganizationUnit.name)
        .all()
    )


def _all_positions(db: Session, amo_id: str) -> list[org_models.OrganizationPosition]:
    return (
        db.query(org_models.OrganizationPosition)
        .filter(org_models.OrganizationPosition.amo_id == amo_id)
        .order_by(org_models.OrganizationPosition.title)
        .all()
    )


def _descendant_unit_ids(units: Iterable[org_models.OrganizationUnit], roots: set[str]) -> set[str]:
    children: dict[Optional[str], list[str]] = {}
    for unit in units:
        children.setdefault(str(unit.parent_id) if unit.parent_id else None, []).append(str(unit.id))
    result = set(roots)
    stack = list(roots)
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            if child not in result:
                result.add(child)
                stack.append(child)
    return result


def _manageable_unit_ids(db: Session, amo_id: str, actor: models.User) -> set[str]:
    units = _all_units(db, amo_id)
    if _is_admin_actor(actor):
        return {str(unit.id) for unit in units if unit.is_active}

    actor_id = str(actor.id)
    roots = {
        str(unit.id)
        for unit in units
        if unit.is_active
        and actor_id
        in {
            str(unit.manager_user_id) if unit.manager_user_id else "",
            str(unit.deputy_manager_user_id) if unit.deputy_manager_user_id else "",
            str(unit.accountable_manager_user_id) if unit.accountable_manager_user_id else "",
        }
    }
    supervisory_units = (
        db.query(org_models.OrganizationPosition.unit_id)
        .join(
            org_models.PositionAssignment,
            org_models.PositionAssignment.position_id == org_models.OrganizationPosition.id,
        )
        .filter(
            *_active_assignment_filter(amo_id),
            org_models.PositionAssignment.user_id == actor_id,
            org_models.PositionAssignment.is_primary.is_(True),
            org_models.OrganizationPosition.is_supervisory.is_(True),
            org_models.OrganizationPosition.is_active.is_(True),
        )
        .all()
    )
    roots.update(str(row[0]) for row in supervisory_units)
    return _descendant_unit_ids(units, roots)


def _manager_scope(db: Session, actor: models.User) -> tuple[str, set[str]]:
    amo_id = _amo_id(actor)
    if _is_admin_actor(actor):
        raise HTTPException(
            status_code=409,
            detail="Use the elevated tenant-administration reporting endpoint for this change.",
        )
    scope = _manageable_unit_ids(db, amo_id, actor)
    if not scope:
        raise HTTPException(
            status_code=403,
            detail="No managed organization unit is assigned to this account.",
        )
    return amo_id, scope


def _position_or_404(db: Session, amo_id: str, position_id: str) -> org_models.OrganizationPosition:
    row = (
        db.query(org_models.OrganizationPosition)
        .filter(
            org_models.OrganizationPosition.id == position_id,
            org_models.OrganizationPosition.amo_id == amo_id,
            org_models.OrganizationPosition.is_active.is_(True),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Active position not found in this tenant.")
    return row


def _unit_or_404(db: Session, amo_id: str, unit_id: str) -> org_models.OrganizationUnit:
    row = (
        db.query(org_models.OrganizationUnit)
        .filter(
            org_models.OrganizationUnit.id == unit_id,
            org_models.OrganizationUnit.amo_id == amo_id,
            org_models.OrganizationUnit.is_active.is_(True),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Active organization unit not found.")
    return row


def _tenant_user(db: Session, amo_id: str, user_id: str, active: bool = True) -> models.User:
    query = db.query(models.User).filter(models.User.id == user_id, models.User.amo_id == amo_id)
    if active:
        query = query.filter(models.User.is_active.is_(True))
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Active tenant user not found.")
    return row


def _assert_position_cycle(
    db: Session,
    amo_id: str,
    position_id: Optional[str],
    parent_position_id: Optional[str],
) -> None:
    if not parent_position_id:
        return
    if position_id and str(position_id) == str(parent_position_id):
        raise HTTPException(status_code=409, detail="A position cannot report to itself.")
    cursor = _position_or_404(db, amo_id, parent_position_id)
    visited: set[str] = set()
    while cursor:
        cursor_id = str(cursor.id)
        if cursor_id in visited:
            raise HTTPException(status_code=409, detail="The current position hierarchy contains a cycle.")
        visited.add(cursor_id)
        if position_id and cursor_id == str(position_id):
            raise HTTPException(status_code=409, detail="This reporting line would create a circular hierarchy.")
        if not cursor.reports_to_position_id:
            break
        cursor = _position_or_404(db, amo_id, str(cursor.reports_to_position_id))


def _assert_manager_cycle(db: Session, amo_id: str, user_id: str, manager_user_id: Optional[str]) -> None:
    if not manager_user_id:
        return
    if str(user_id) == str(manager_user_id):
        raise HTTPException(status_code=409, detail="A person cannot report to themselves.")
    visited = {str(user_id)}
    cursor_id: Optional[str] = str(manager_user_id)
    while cursor_id:
        if cursor_id in visited:
            raise HTTPException(status_code=409, detail="This reporting manager would create a circular management chain.")
        visited.add(cursor_id)
        row = (
            db.query(org_models.PositionAssignment)
            .filter(
                *_active_assignment_filter(amo_id),
                org_models.PositionAssignment.user_id == cursor_id,
                org_models.PositionAssignment.is_primary.is_(True),
            )
            .order_by(org_models.PositionAssignment.effective_from.desc())
            .first()
        )
        cursor_id = str(row.reporting_manager_user_id) if row and row.reporting_manager_user_id else None


def _ancestor_positions(
    position: org_models.OrganizationPosition,
    positions_by_id: dict[str, org_models.OrganizationPosition],
) -> list[org_models.OrganizationPosition]:
    result: list[org_models.OrganizationPosition] = []
    visited = {str(position.id)}
    parent_id = str(position.reports_to_position_id) if position.reports_to_position_id else None
    while parent_id:
        if parent_id in visited:
            break
        visited.add(parent_id)
        parent = positions_by_id.get(parent_id)
        if not parent:
            break
        result.append(parent)
        parent_id = str(parent.reports_to_position_id) if parent.reports_to_position_id else None
    return result


def _manager_candidates(
    db: Session,
    amo_id: str,
    position: org_models.OrganizationPosition,
) -> list[line_schemas.ReportingManagerCandidateRead]:
    positions = {str(row.id): row for row in _all_positions(db, amo_id)}
    result: list[line_schemas.ReportingManagerCandidateRead] = []
    for index, ancestor in enumerate(_ancestor_positions(position, positions)):
        rows = (
            db.query(org_models.PositionAssignment, models.User)
            .join(models.User, models.User.id == org_models.PositionAssignment.user_id)
            .filter(
                *_active_assignment_filter(amo_id),
                org_models.PositionAssignment.position_id == ancestor.id,
                org_models.PositionAssignment.is_primary.is_(True),
                models.User.is_active.is_(True),
            )
            .order_by(models.User.full_name)
            .all()
        )
        for assignment, user in rows:
            result.append(
                line_schemas.ReportingManagerCandidateRead(
                    user_id=str(user.id),
                    user_name=user.full_name,
                    position_id=str(ancestor.id),
                    position_title=ancestor.title,
                    relationship="DIRECT_PARENT" if index == 0 else "ANCESTOR",
                )
            )
    return result


def _resolve_manager(
    db: Session,
    amo_id: str,
    position: org_models.OrganizationPosition,
    requested_user_id: Optional[str],
    *,
    matrix_reporting: bool,
    matrix_reason: Optional[str],
) -> Optional[models.User]:
    candidates = _manager_candidates(db, amo_id, position)
    candidate_ids = {item.user_id for item in candidates}
    if requested_user_id:
        manager = _tenant_user(db, amo_id, requested_user_id)
        if str(manager.id) not in candidate_ids:
            if not matrix_reporting or not str(matrix_reason or "").strip():
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "The selected manager does not occupy the direct parent or an ancestor position. "
                        "Use a documented matrix-reporting exception to select someone outside the position chain."
                    ),
                )
        return manager

    if not position.reports_to_position_id:
        return None
    direct = [item for item in candidates if item.relationship == "DIRECT_PARENT"]
    if len(direct) == 1:
        return _tenant_user(db, amo_id, direct[0].user_id)
    if len(direct) > 1:
        raise HTTPException(
            status_code=422,
            detail="The parent position has several occupants. Select the actual reporting manager.",
        )
    nearest_relationship: Optional[str] = None
    nearest: list[line_schemas.ReportingManagerCandidateRead] = []
    for item in candidates:
        if nearest_relationship is None:
            nearest_relationship = item.position_id
        if item.position_id != nearest_relationship:
            break
        nearest.append(item)
    if len(nearest) == 1:
        return _tenant_user(db, amo_id, nearest[0].user_id)
    if nearest:
        raise HTTPException(
            status_code=422,
            detail="The nearest occupied ancestor position has several occupants. Select the actual manager.",
        )
    raise HTTPException(
        status_code=422,
        detail="No occupied parent position was found. Assign the supervisory position first or select a matrix manager with a reason.",
    )


def _approved_preference_map(
    db: Session,
    assignment_ids: Iterable[str],
) -> dict[str, line_models.PersonnelTitlePreference]:
    ids = list({str(value) for value in assignment_ids})
    if not ids:
        return {}
    rows = (
        db.query(line_models.PersonnelTitlePreference)
        .filter(
            line_models.PersonnelTitlePreference.assignment_id.in_(ids),
            line_models.PersonnelTitlePreference.status == "APPROVED",
        )
        .order_by(
            line_models.PersonnelTitlePreference.decided_at.desc(),
            line_models.PersonnelTitlePreference.created_at.desc(),
        )
        .all()
    )
    result: dict[str, line_models.PersonnelTitlePreference] = {}
    for row in rows:
        result.setdefault(str(row.assignment_id), row)
    return result


def _latest_preference_map(
    db: Session,
    assignment_ids: Iterable[str],
) -> dict[str, line_models.PersonnelTitlePreference]:
    ids = list({str(value) for value in assignment_ids})
    if not ids:
        return {}
    rows = (
        db.query(line_models.PersonnelTitlePreference)
        .filter(line_models.PersonnelTitlePreference.assignment_id.in_(ids))
        .order_by(
            line_models.PersonnelTitlePreference.requested_at.desc(),
            line_models.PersonnelTitlePreference.created_at.desc(),
        )
        .all()
    )
    result: dict[str, line_models.PersonnelTitlePreference] = {}
    for row in rows:
        result.setdefault(str(row.assignment_id), row)
    return result


def _preference_read(
    db: Session,
    row: line_models.PersonnelTitlePreference,
) -> line_schemas.TitlePreferenceRead:
    user = db.query(models.User).filter(models.User.id == row.user_id).first()
    assignment = (
        db.query(org_models.PositionAssignment)
        .filter(org_models.PositionAssignment.id == row.assignment_id)
        .first()
    )
    position = (
        db.query(org_models.OrganizationPosition)
        .filter(org_models.OrganizationPosition.id == assignment.position_id)
        .first()
        if assignment
        else None
    )
    return line_schemas.TitlePreferenceRead(
        id=str(row.id),
        user_id=str(row.user_id),
        user_name=user.full_name if user else "Unknown user",
        assignment_id=str(row.assignment_id),
        canonical_title=position.title if position else "Unknown position",
        requested_title=row.requested_title,
        reason=row.reason,
        source=row.source,
        status=row.status,
        requested_by_user_id=row.requested_by_user_id,
        decided_by_user_id=row.decided_by_user_id,
        requested_at=row.requested_at,
        decided_at=row.decided_at,
    )


def _visible_user_ids(
    db: Session,
    amo_id: str,
    actor: models.User,
    manageable_unit_ids: set[str],
) -> set[str]:
    if _is_admin_actor(actor):
        return {
            str(row[0])
            for row in db.query(models.User.id)
            .filter(models.User.amo_id == amo_id, models.User.is_active.is_(True))
            .all()
        }
    units = _all_units(db, amo_id)
    department_ids = {
        str(unit.department_id)
        for unit in units
        if str(unit.id) in manageable_unit_ids and unit.department_id
    }
    result = {
        str(row[0])
        for row in db.query(models.User.id)
        .filter(
            models.User.amo_id == amo_id,
            models.User.is_active.is_(True),
            models.User.department_id.in_(list(department_ids)) if department_ids else False,
        )
        .all()
    }
    position_ids = {
        str(row[0])
        for row in db.query(org_models.OrganizationPosition.id)
        .filter(
            org_models.OrganizationPosition.amo_id == amo_id,
            org_models.OrganizationPosition.unit_id.in_(list(manageable_unit_ids)),
        )
        .all()
    }
    if position_ids:
        result.update(
            str(row[0])
            for row in db.query(org_models.PositionAssignment.user_id)
            .filter(
                *_active_assignment_filter(amo_id),
                org_models.PositionAssignment.position_id.in_(list(position_ids)),
            )
            .all()
        )
    result.update(
        str(row[0])
        for row in db.query(org_models.PositionAssignment.user_id)
        .filter(
            *_active_assignment_filter(amo_id),
            org_models.PositionAssignment.reporting_manager_user_id == str(actor.id),
        )
        .all()
    )
    result.add(str(actor.id))
    return result


def _workspace(db: Session, actor: models.User) -> line_schemas.ReportingWorkspaceRead:
    amo_id = _amo_id(actor)
    all_units = _all_units(db, amo_id)
    all_positions = _all_positions(db, amo_id)
    positions_by_id = {str(row.id): row for row in all_positions}
    manageable = _manageable_unit_ids(db, amo_id, actor)
    if not manageable and not _is_admin_actor(actor):
        raise HTTPException(status_code=403, detail="No reporting-line management scope is assigned.")

    visible_position_ids = {
        str(position.id)
        for position in all_positions
        if str(position.unit_id) in manageable and position.is_active
    }
    for position_id in list(visible_position_ids):
        position = positions_by_id[position_id]
        visible_position_ids.update(str(item.id) for item in _ancestor_positions(position, positions_by_id))
    visible_positions = [row for row in all_positions if str(row.id) in visible_position_ids]
    visible_unit_ids = set(manageable)
    visible_unit_ids.update(str(row.unit_id) for row in visible_positions)
    visible_units = [row for row in all_units if str(row.id) in visible_unit_ids]

    assignments = []
    if visible_position_ids:
        assignments = (
            db.query(org_models.PositionAssignment, models.User)
            .join(models.User, models.User.id == org_models.PositionAssignment.user_id)
            .filter(
                *_active_assignment_filter(amo_id),
                org_models.PositionAssignment.position_id.in_(list(visible_position_ids)),
                models.User.is_active.is_(True),
            )
            .order_by(models.User.full_name)
            .all()
        )
    assignment_ids = [str(assignment.id) for assignment, _ in assignments]
    approved = _approved_preference_map(db, assignment_ids)
    latest = _latest_preference_map(db, assignment_ids)
    managers = {
        str(row.id): row.full_name
        for row in db.query(models.User)
        .filter(models.User.amo_id == amo_id)
        .all()
    }
    assignments_by_position: dict[str, list[line_schemas.ReportingOccupantRead]] = {}
    for assignment, user in assignments:
        position = positions_by_id.get(str(assignment.position_id))
        if not position:
            continue
        preference = approved.get(str(assignment.id))
        latest_preference = latest.get(str(assignment.id))
        assignments_by_position.setdefault(str(position.id), []).append(
            line_schemas.ReportingOccupantRead(
                assignment_id=str(assignment.id),
                user_id=str(user.id),
                user_name=user.full_name,
                staff_code=user.staff_code,
                canonical_title=position.title,
                display_title=preference.requested_title if preference else position.title,
                title_preference_status=latest_preference.status if latest_preference else None,
                reporting_manager_user_id=assignment.reporting_manager_user_id,
                reporting_manager_name=managers.get(str(assignment.reporting_manager_user_id)) if assignment.reporting_manager_user_id else None,
                assignment_type=assignment.assignment_type,
                is_primary=bool(assignment.is_primary),
                effective_from=assignment.effective_from,
                effective_to=assignment.effective_to,
            )
        )

    unit_names = {str(unit.id): unit.name for unit in all_units}
    position_reads: list[line_schemas.ReportingPositionRead] = []
    for position in visible_positions:
        ancestors = _ancestor_positions(position, positions_by_id)
        path = [item.title for item in reversed(ancestors)] + [position.title]
        occupants = assignments_by_position.get(str(position.id), [])
        candidates: list[line_schemas.ReportingManagerCandidateRead] = []
        for index, ancestor in enumerate(ancestors):
            for occupant in assignments_by_position.get(str(ancestor.id), []):
                if not occupant.is_primary:
                    continue
                candidates.append(
                    line_schemas.ReportingManagerCandidateRead(
                        user_id=occupant.user_id,
                        user_name=occupant.user_name,
                        position_id=str(ancestor.id),
                        position_title=ancestor.title,
                        relationship="DIRECT_PARENT" if index == 0 else "ANCESTOR",
                    )
                )
        occupied_count = len(occupants)
        position_reads.append(
            line_schemas.ReportingPositionRead(
                id=str(position.id),
                unit_id=str(position.unit_id),
                unit_name=unit_names.get(str(position.unit_id), "Unknown unit"),
                code=position.code,
                canonical_title=position.title,
                reports_to_position_id=position.reports_to_position_id,
                reports_to_title=positions_by_id.get(str(position.reports_to_position_id)).title if position.reports_to_position_id and positions_by_id.get(str(position.reports_to_position_id)) else None,
                depth=len(ancestors),
                path_titles=path,
                is_supervisory=bool(position.is_supervisory),
                is_regulatory_post=bool(position.is_regulatory_post),
                authority_acceptance_required=bool(position.authority_acceptance_required),
                headcount_limit=int(position.headcount_limit or 1),
                occupied_count=occupied_count,
                vacancy_count=max(0, int(position.headcount_limit or 1) - occupied_count),
                editable=str(position.unit_id) in manageable,
                manager_candidates=candidates,
                occupants=occupants,
            )
        )
    position_reads.sort(key=lambda item: (item.path_titles, item.unit_name, item.canonical_title))

    visible_user_ids = _visible_user_ids(db, amo_id, actor, manageable)
    users = (
        db.query(models.User)
        .filter(
            models.User.amo_id == amo_id,
            models.User.is_active.is_(True),
            models.User.id.in_(list(visible_user_ids)),
        )
        .order_by(models.User.full_name)
        .all()
        if visible_user_ids
        else []
    )
    scoped_assignment_ids = {
        str(assignment.id)
        for assignment, _ in assignments
        if str(positions_by_id[str(assignment.position_id)].unit_id) in manageable
    }
    pending_rows = (
        db.query(line_models.PersonnelTitlePreference)
        .filter(
            line_models.PersonnelTitlePreference.amo_id == amo_id,
            line_models.PersonnelTitlePreference.status == "PENDING",
            line_models.PersonnelTitlePreference.assignment_id.in_(list(scoped_assignment_ids)),
        )
        .order_by(line_models.PersonnelTitlePreference.requested_at)
        .all()
        if scoped_assignment_ids
        else []
    )
    return line_schemas.ReportingWorkspaceRead(
        actor_mode="ADMIN" if _is_admin_actor(actor) else "MANAGER",
        can_manage_all=_is_admin_actor(actor),
        manageable_unit_ids=sorted(manageable),
        units=[
            line_schemas.ReportingUnitRead(
                id=str(unit.id),
                code=unit.code,
                name=unit.name,
                unit_type=unit.unit_type,
                parent_id=unit.parent_id,
                department_id=unit.department_id,
                editable=str(unit.id) in manageable,
            )
            for unit in visible_units
        ],
        positions=position_reads,
        users=[
            line_schemas.ReportingReferenceUser(
                id=str(user.id),
                full_name=user.full_name,
                staff_code=user.staff_code,
                email=user.email,
                department_id=user.department_id,
                current_title=user.position_title,
            )
            for user in users
        ],
        pending_title_preferences=[_preference_read(db, row) for row in pending_rows],
        authorization_boundary=AUTHORIZATION_BOUNDARY,
    )


def _unique_position_code(
    db: Session,
    amo_id: str,
    unit: org_models.OrganizationUnit,
    title: str,
    requested: Optional[str],
) -> str:
    base = _normalise_code(requested or f"{unit.code}_{title}")[:58] or "POSITION"
    candidate = base
    counter = 2
    while (
        db.query(org_models.OrganizationPosition.id)
        .filter(
            org_models.OrganizationPosition.amo_id == amo_id,
            org_models.OrganizationPosition.code == candidate,
        )
        .first()
    ):
        suffix = f"_{counter}"
        candidate = f"{base[:64-len(suffix)]}{suffix}"
        counter += 1
    return candidate


def _create_chain(
    db: Session,
    actor: models.User,
    payload: line_schemas.ReportingChainCreate,
    *,
    manager_mode: bool,
) -> list[org_models.OrganizationPosition]:
    amo_id = _amo_id(actor)
    scope = _manageable_unit_ids(db, amo_id, actor)
    if manager_mode and str(payload.unit_id) not in scope:
        raise HTTPException(status_code=403, detail="The selected unit is outside your management scope.")
    unit = _unit_or_404(db, amo_id, payload.unit_id)
    parent_id = payload.parent_position_id
    if parent_id:
        parent = _position_or_404(db, amo_id, parent_id)
        if manager_mode and str(parent.unit_id) not in scope:
            raise HTTPException(status_code=403, detail="The parent position is outside your management scope.")
    created: list[org_models.OrganizationPosition] = []
    for role in payload.roles:
        title = role.title.strip()
        code = _unique_position_code(db, amo_id, unit, title, role.code)
        row = org_models.OrganizationPosition(
            amo_id=amo_id,
            unit_id=unit.id,
            reports_to_position_id=parent_id,
            code=code,
            title=title,
            employment_category="EMPLOYEE",
            headcount_limit=role.headcount_limit,
            is_supervisory=role.is_supervisory,
            is_regulatory_post=False,
            authority_acceptance_required=False,
            succession_criticality="STANDARD",
            is_active=True,
            created_by_user_id=actor.id,
        )
        db.add(row)
        db.flush()
        audit_services.log_event(
            db,
            amo_id=amo_id,
            actor_user_id=str(actor.id),
            entity_type="accounts.organization_position",
            entity_id=str(row.id),
            action="REPORTING_CHAIN_POSITION_CREATED",
            after={
                "code": row.code,
                "title": row.title,
                "unit_id": str(row.unit_id),
                "reports_to_position_id": str(parent_id) if parent_id else None,
                "authorization_changed": False,
            },
            metadata={"module": "accounts", "source": "reporting_line_builder"},
        )
        created.append(row)
        parent_id = str(row.id)
    return created


def _update_position(
    db: Session,
    actor: models.User,
    position_id: str,
    payload: line_schemas.ReportingPositionUpdate,
    *,
    manager_mode: bool,
) -> org_models.OrganizationPosition:
    amo_id = _amo_id(actor)
    scope = _manageable_unit_ids(db, amo_id, actor)
    position = _position_or_404(db, amo_id, position_id)
    if manager_mode and str(position.unit_id) not in scope:
        raise HTTPException(status_code=403, detail="This position is outside your management scope.")
    if manager_mode and position.is_regulatory_post:
        raise HTTPException(status_code=403, detail="Regulatory or nominated positions require tenant-administrator control.")
    changes = payload.model_dump(exclude_unset=True)
    sync = bool(changes.pop("sync_reporting_managers", True))
    if "reports_to_position_id" in changes:
        parent_id = changes["reports_to_position_id"]
        _assert_position_cycle(db, amo_id, str(position.id), parent_id)
        if parent_id and manager_mode:
            parent = _position_or_404(db, amo_id, parent_id)
            if str(parent.unit_id) not in scope:
                raise HTTPException(status_code=403, detail="The parent position is outside your management scope.")
    if "headcount_limit" in changes:
        occupied = int(
            db.query(func.count(org_models.PositionAssignment.id))
            .filter(
                *_active_assignment_filter(amo_id),
                org_models.PositionAssignment.position_id == position.id,
            )
            .scalar()
            or 0
        )
        if int(changes["headcount_limit"]) < occupied:
            raise HTTPException(status_code=409, detail="Headcount cannot be reduced below current active occupancy.")
    if "title" in changes:
        changes["title"] = str(changes["title"]).strip()
    before = {key: getattr(position, key) for key in changes}
    for key, value in changes.items():
        setattr(position, key, value)
    db.flush()

    active_assignments = (
        db.query(org_models.PositionAssignment)
        .filter(
            *_active_assignment_filter(amo_id),
            org_models.PositionAssignment.position_id == position.id,
        )
        .all()
    )
    approved = _approved_preference_map(db, [str(row.id) for row in active_assignments])
    if "title" in changes:
        for assignment in active_assignments:
            if str(assignment.id) in approved:
                continue
            user = db.query(models.User).filter(models.User.id == assignment.user_id).first()
            if user:
                user.position_title = position.title
                db.add(user)
    if sync and "reports_to_position_id" in changes:
        candidates = _manager_candidates(db, amo_id, position)
        direct = [item for item in candidates if item.relationship == "DIRECT_PARENT"]
        auto_manager_id = direct[0].user_id if len(direct) == 1 else None
        if auto_manager_id:
            for assignment in active_assignments:
                _assert_manager_cycle(db, amo_id, str(assignment.user_id), auto_manager_id)
                assignment.reporting_manager_user_id = auto_manager_id
                db.add(assignment)
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        entity_type="accounts.organization_position",
        entity_id=str(position.id),
        action="REPORTING_POSITION_UPDATED",
        before=before,
        after={**changes, "authorization_changed": False},
        metadata={"module": "accounts", "source": "reporting_line_builder"},
    )
    return position


def _create_approved_preference(
    db: Session,
    *,
    amo_id: str,
    user: models.User,
    assignment: org_models.PositionAssignment,
    title: str,
    actor: models.User,
    source: str,
) -> line_models.PersonnelTitlePreference:
    now = datetime.now(timezone.utc)
    existing = (
        db.query(line_models.PersonnelTitlePreference)
        .filter(
            line_models.PersonnelTitlePreference.assignment_id == assignment.id,
            line_models.PersonnelTitlePreference.status == "APPROVED",
        )
        .all()
    )
    for row in existing:
        row.status = "SUPERSEDED"
        row.decided_at = now
        db.add(row)
    preference = line_models.PersonnelTitlePreference(
        amo_id=amo_id,
        user_id=user.id,
        assignment_id=assignment.id,
        requested_title=title.strip(),
        source=source,
        status="APPROVED",
        requested_by_user_id=actor.id,
        decided_by_user_id=actor.id,
        requested_at=now,
        decided_at=now,
    )
    db.add(preference)
    user.position_title = preference.requested_title
    db.add(user)
    return preference


def _create_assignment(
    db: Session,
    actor: models.User,
    payload: line_schemas.GuidedAssignmentCreate,
    *,
    manager_mode: bool,
) -> org_models.PositionAssignment:
    amo_id = _amo_id(actor)
    scope = _manageable_unit_ids(db, amo_id, actor)
    position = _position_or_404(db, amo_id, payload.position_id)
    if manager_mode and str(position.unit_id) not in scope:
        raise HTTPException(status_code=403, detail="The selected position is outside your management scope.")
    if manager_mode and (position.is_regulatory_post or position.authority_acceptance_required):
        raise HTTPException(status_code=403, detail="Regulatory and authority-accepted assignments require tenant-administrator control.")
    user = _tenant_user(db, amo_id, payload.user_id)
    if manager_mode:
        allowed_users = _visible_user_ids(db, amo_id, actor, scope)
        if str(user.id) not in allowed_users:
            raise HTTPException(status_code=403, detail="The selected person is outside your department-management scope.")
    assignment_type = payload.assignment_type.strip().upper()
    if assignment_type not in ALLOWED_ASSIGNMENT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported assignment type.")
    _date_order(payload.effective_from, payload.effective_to, "Assignment")
    if payload.matrix_reporting and not str(payload.matrix_reason or "").strip():
        raise HTTPException(status_code=422, detail="A reason is required for matrix reporting.")
    if payload.is_primary:
        existing = (
            db.query(org_models.PositionAssignment)
            .filter(
                *_active_assignment_filter(amo_id, payload.effective_from),
                org_models.PositionAssignment.user_id == user.id,
                org_models.PositionAssignment.is_primary.is_(True),
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="The person already has an active primary assignment.")
    occupied = int(
        db.query(func.count(org_models.PositionAssignment.id))
        .filter(
            *_active_assignment_filter(amo_id, payload.effective_from),
            org_models.PositionAssignment.position_id == position.id,
        )
        .scalar()
        or 0
    )
    if occupied >= int(position.headcount_limit or 1):
        raise HTTPException(status_code=409, detail="The approved headcount for this position is filled.")
    if position.is_regulatory_post and not payload.appointment_reference:
        raise HTTPException(status_code=422, detail="An appointment reference is required for this regulatory position.")
    if position.authority_acceptance_required and not payload.authority_acceptance_reference:
        raise HTTPException(status_code=422, detail="Authority acceptance evidence is required for this position.")
    manager = _resolve_manager(
        db,
        amo_id,
        position,
        payload.reporting_manager_user_id,
        matrix_reporting=payload.matrix_reporting,
        matrix_reason=payload.matrix_reason,
    )
    _assert_manager_cycle(db, amo_id, str(user.id), str(manager.id) if manager else None)
    row = org_models.PositionAssignment(
        amo_id=amo_id,
        user_id=user.id,
        position_id=position.id,
        reporting_manager_user_id=manager.id if manager else None,
        assignment_type=assignment_type,
        status="ACTIVE",
        is_primary=payload.is_primary,
        matrix_reporting=payload.matrix_reporting,
        matrix_reason=payload.matrix_reason,
        fte_percent=Decimal(str(payload.fte_percent)),
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        appointment_reference=payload.appointment_reference,
        authority_acceptance_reference=payload.authority_acceptance_reference,
        authority_accepted_on=payload.authority_accepted_on,
        delegation_limitations=payload.delegation_limitations,
        created_by_user_id=actor.id,
        approved_by_user_id=actor.id,
        approved_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    display_title = str(payload.display_title or "").strip()
    if display_title and display_title.casefold() != position.title.casefold():
        _create_approved_preference(
            db,
            amo_id=amo_id,
            user=user,
            assignment=row,
            title=display_title,
            actor=actor,
            source="MANAGER_SET" if manager_mode else "ADMIN_SET",
        )
    elif payload.is_primary:
        user.position_title = position.title
        db.add(user)
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        entity_type="accounts.position_assignment",
        entity_id=str(row.id),
        action="GUIDED_ASSIGNMENT_CREATED",
        after={
            "user_id": str(user.id),
            "position_id": str(position.id),
            "reporting_manager_user_id": str(manager.id) if manager else None,
            "display_title": display_title or position.title,
            "authorization_changed": False,
        },
        metadata={"module": "accounts", "source": "reporting_line_builder"},
    )
    return row


def _preference_in_scope(
    db: Session,
    actor: models.User,
    preference_id: str,
    *,
    manager_mode: bool,
) -> line_models.PersonnelTitlePreference:
    amo_id = _amo_id(actor)
    preference = (
        db.query(line_models.PersonnelTitlePreference)
        .filter(
            line_models.PersonnelTitlePreference.id == preference_id,
            line_models.PersonnelTitlePreference.amo_id == amo_id,
        )
        .first()
    )
    if not preference:
        raise HTTPException(status_code=404, detail="Title preference request not found.")
    assignment = (
        db.query(org_models.PositionAssignment)
        .filter(org_models.PositionAssignment.id == preference.assignment_id)
        .first()
    )
    position = _position_or_404(db, amo_id, str(assignment.position_id)) if assignment else None
    if not position:
        raise HTTPException(status_code=409, detail="The related position assignment is unavailable.")
    if manager_mode and str(position.unit_id) not in _manageable_unit_ids(db, amo_id, actor):
        raise HTTPException(status_code=403, detail="This request is outside your management scope.")
    return preference


def _decide_preference(
    db: Session,
    actor: models.User,
    preference_id: str,
    payload: line_schemas.TitlePreferenceDecision,
    *,
    manager_mode: bool,
) -> line_models.PersonnelTitlePreference:
    preference = _preference_in_scope(db, actor, preference_id, manager_mode=manager_mode)
    if preference.status != "PENDING":
        raise HTTPException(status_code=409, detail="Only pending title requests can be decided.")
    decision = payload.decision.upper()
    now = datetime.now(timezone.utc)
    if decision == "APPROVE":
        previous = (
            db.query(line_models.PersonnelTitlePreference)
            .filter(
                line_models.PersonnelTitlePreference.assignment_id == preference.assignment_id,
                line_models.PersonnelTitlePreference.status == "APPROVED",
            )
            .all()
        )
        for row in previous:
            row.status = "SUPERSEDED"
            row.decided_at = now
            db.add(row)
        preference.status = "APPROVED"
        user = db.query(models.User).filter(models.User.id == preference.user_id).first()
        if user:
            user.position_title = preference.requested_title
            db.add(user)
    else:
        preference.status = "REJECTED"
    preference.decided_by_user_id = actor.id
    preference.decided_at = now
    db.add(preference)
    audit_services.log_event(
        db,
        amo_id=str(preference.amo_id),
        actor_user_id=str(actor.id),
        entity_type="accounts.personnel_title_preference",
        entity_id=str(preference.id),
        action=f"TITLE_PREFERENCE_{preference.status}",
        after={
            "requested_title": preference.requested_title,
            "decision_note": payload.note,
            "authorization_changed": False,
        },
        metadata={"module": "accounts", "source": "title_preference"},
    )
    return preference


def _current_primary_assignment(db: Session, amo_id: str, user_id: str):
    return (
        db.query(org_models.PositionAssignment)
        .filter(
            *_active_assignment_filter(amo_id),
            org_models.PositionAssignment.user_id == user_id,
            org_models.PositionAssignment.is_primary.is_(True),
        )
        .order_by(org_models.PositionAssignment.effective_from.desc())
        .first()
    )


@portal_router.get("/workspace", response_model=line_schemas.ReportingWorkspaceRead)
def reporting_workspace(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    return _workspace(db, current_user)


@portal_router.post("/manager/chains", response_model=line_schemas.ReportingChainResult, status_code=status.HTTP_201_CREATED)
def manager_create_chain(
    payload: line_schemas.ReportingChainCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _manager_scope(db, current_user)
    rows = _create_chain(db, current_user, payload, manager_mode=True)
    db.commit()
    return line_schemas.ReportingChainResult(
        created_positions=[
            item
            for item in _workspace(db, current_user).positions
            if item.id in {str(row.id) for row in rows}
        ]
    )


@portal_router.patch("/manager/positions/{position_id}", response_model=line_schemas.ReportingWorkspaceRead)
def manager_update_position(
    position_id: str,
    payload: line_schemas.ReportingPositionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _manager_scope(db, current_user)
    _update_position(db, current_user, position_id, payload, manager_mode=True)
    db.commit()
    return _workspace(db, current_user)


@portal_router.post("/manager/assignments", response_model=line_schemas.ReportingWorkspaceRead, status_code=status.HTTP_201_CREATED)
def manager_create_assignment(
    payload: line_schemas.GuidedAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _manager_scope(db, current_user)
    _create_assignment(db, current_user, payload, manager_mode=True)
    db.commit()
    return _workspace(db, current_user)


@portal_router.post("/manager/title-preferences/{preference_id}/decision", response_model=line_schemas.ReportingWorkspaceRead)
def manager_decide_title(
    preference_id: str,
    payload: line_schemas.TitlePreferenceDecision,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _manager_scope(db, current_user)
    _decide_preference(db, current_user, preference_id, payload, manager_mode=True)
    db.commit()
    return _workspace(db, current_user)


@portal_router.get("/my-title", response_model=line_schemas.MyTitleProfileRead)
def my_title_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    amo_id = _amo_id(current_user)
    assignment = _current_primary_assignment(db, amo_id, str(current_user.id))
    if not assignment:
        return line_schemas.MyTitleProfileRead(authorization_boundary=AUTHORIZATION_BOUNDARY)
    position = _position_or_404(db, amo_id, str(assignment.position_id))
    positions = {str(row.id): row for row in _all_positions(db, amo_id)}
    approved = _approved_preference_map(db, [str(assignment.id)]).get(str(assignment.id))
    latest = _latest_preference_map(db, [str(assignment.id)]).get(str(assignment.id))
    unit = _unit_or_404(db, amo_id, str(position.unit_id))
    manager = (
        db.query(models.User).filter(models.User.id == assignment.reporting_manager_user_id).first()
        if assignment.reporting_manager_user_id
        else None
    )
    chain = [item.title for item in reversed(_ancestor_positions(position, positions))] + [position.title]
    return line_schemas.MyTitleProfileRead(
        assignment_id=str(assignment.id),
        position_id=str(position.id),
        canonical_title=position.title,
        display_title=approved.requested_title if approved else position.title,
        unit_name=unit.name,
        reporting_manager_name=manager.full_name if manager else None,
        reporting_chain=chain,
        current_preference=_preference_read(db, latest) if latest else None,
        authorization_boundary=AUTHORIZATION_BOUNDARY,
    )


@portal_router.put("/my-title", response_model=line_schemas.MyTitleProfileRead)
def submit_my_title_preference(
    payload: line_schemas.TitlePreferenceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    amo_id = _amo_id(current_user)
    assignment = _current_primary_assignment(db, amo_id, str(current_user.id))
    if not assignment:
        raise HTTPException(status_code=409, detail="A current primary assignment is required before requesting a display title.")
    position = _position_or_404(db, amo_id, str(assignment.position_id))
    title = payload.requested_title.strip()
    if title.casefold() == position.title.casefold():
        return clear_my_title_preference(db=db, current_user=current_user)
    pending = (
        db.query(line_models.PersonnelTitlePreference)
        .filter(
            line_models.PersonnelTitlePreference.assignment_id == assignment.id,
            line_models.PersonnelTitlePreference.status == "PENDING",
        )
        .all()
    )
    for row in pending:
        row.status = "WITHDRAWN"
        row.decided_at = datetime.now(timezone.utc)
        db.add(row)
    row = line_models.PersonnelTitlePreference(
        amo_id=amo_id,
        user_id=current_user.id,
        assignment_id=assignment.id,
        requested_title=title,
        reason=payload.reason,
        source="SELF_SERVICE",
        status="PENDING",
        requested_by_user_id=current_user.id,
        requested_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.personnel_title_preference",
        entity_id=str(row.id),
        action="TITLE_PREFERENCE_REQUESTED",
        after={"requested_title": title, "authorization_changed": False},
        metadata={"module": "accounts", "source": "self_service"},
    )
    db.commit()
    return my_title_profile(db=db, current_user=current_user)


@portal_router.post("/my-title/clear", response_model=line_schemas.MyTitleProfileRead)
def clear_my_title_preference(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    amo_id = _amo_id(current_user)
    assignment = _current_primary_assignment(db, amo_id, str(current_user.id))
    if not assignment:
        return line_schemas.MyTitleProfileRead(authorization_boundary=AUTHORIZATION_BOUNDARY)
    position = _position_or_404(db, amo_id, str(assignment.position_id))
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
    current_user.position_title = position.title
    db.add(current_user)
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.position_assignment",
        entity_id=str(assignment.id),
        action="DISPLAY_TITLE_RESET",
        after={"display_title": position.title, "authorization_changed": False},
        metadata={"module": "accounts", "source": "self_service"},
    )
    db.commit()
    return my_title_profile(db=db, current_user=current_user)


@admin_router.post("/organization/reporting/chains", response_model=line_schemas.ReportingChainResult, status_code=status.HTTP_201_CREATED)
def admin_create_chain(
    payload: line_schemas.ReportingChainCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    rows = _create_chain(db, current_user, payload, manager_mode=False)
    db.commit()
    workspace = _workspace(db, current_user)
    created_ids = {str(row.id) for row in rows}
    return line_schemas.ReportingChainResult(
        created_positions=[item for item in workspace.positions if item.id in created_ids]
    )


@admin_router.patch("/organization/reporting/positions/{position_id}", response_model=line_schemas.ReportingWorkspaceRead)
def admin_update_position(
    position_id: str,
    payload: line_schemas.ReportingPositionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    _update_position(db, current_user, position_id, payload, manager_mode=False)
    db.commit()
    return _workspace(db, current_user)


@admin_router.post("/organization/reporting/assignments", response_model=line_schemas.ReportingWorkspaceRead, status_code=status.HTTP_201_CREATED)
def admin_create_guided_assignment(
    payload: line_schemas.GuidedAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    _create_assignment(db, current_user, payload, manager_mode=False)
    db.commit()
    return _workspace(db, current_user)


@admin_router.post("/organization/reporting/title-preferences/{preference_id}/decision", response_model=line_schemas.ReportingWorkspaceRead)
def admin_decide_title(
    preference_id: str,
    payload: line_schemas.TitlePreferenceDecision,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    _decide_preference(db, current_user, preference_id, payload, manager_mode=False)
    db.commit()
    return _workspace(db, current_user)
