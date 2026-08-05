"""Corporate structure, workforce assignment and personnel-governance APIs."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_db
from amodb.security import get_current_active_user, require_admin

from . import models
from . import corporate_structure_models as org_models
from . import corporate_structure_schemas as org_schemas
from .router_admin import router

portal_router = APIRouter(prefix="/organization", tags=["organization_portal"])

UNIT_TYPES = {
    "COMPANY", "DIVISION", "DIRECTORATE", "DEPARTMENT", "SECTION",
    "TEAM", "STATION", "BASE", "PROJECT",
}
ASSIGNMENT_TYPES = {
    "SUBSTANTIVE", "ACTING", "SECONDMENT", "TEMPORARY", "INTERIM",
    "INTERNSHIP", "APPRENTICESHIP", "CONTRACT",
}
ENGAGEMENT_TYPES = {
    "EMPLOYEE", "FIXED_TERM", "CONTRACTOR", "CONSULTANT", "INTERN",
    "TRAINEE", "APPRENTICE", "VOLUNTEER", "SECONDED", "TEMPORARY",
}
CONTINGENT_TYPES = ENGAGEMENT_TYPES - {"EMPLOYEE"}
TIME_BOUND_ENGAGEMENTS = ENGAGEMENT_TYPES - {"EMPLOYEE"}
SPONSOR_REQUIRED_ENGAGEMENTS = {
    "CONTRACTOR", "CONSULTANT", "INTERN", "TRAINEE", "APPRENTICE",
    "VOLUNTEER", "SECONDED", "TEMPORARY",
}
ACTIVE_STATUSES = {"ACTIVE", "ACTING", "APPROVED"}


def _target_amo_id(current_user: models.User, requested_amo_id: Optional[str]) -> str:
    target = requested_amo_id if current_user.is_superuser and requested_amo_id else current_user.amo_id
    if not target:
        raise HTTPException(status_code=400, detail="AMO context is required.")
    return str(target)


def _tenant_user(db: Session, *, amo_id: str, user_id: Optional[str], active_required: bool = False) -> Optional[models.User]:
    if not user_id:
        return None
    user = db.query(models.User).filter(models.User.id == user_id, models.User.amo_id == amo_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="The selected user was not found in this AMO.")
    if active_required and not user.is_active:
        raise HTTPException(status_code=409, detail="Inactive users cannot receive a new active corporate assignment.")
    return user


def _date_order(start: Optional[date], end: Optional[date], label: str) -> None:
    if start and end and end < start:
        raise HTTPException(status_code=422, detail=f"{label} end date cannot be before its start date.")


def _normalise_code(value: str) -> str:
    return "_".join(value.strip().upper().replace("-", " ").split())


def _loads_dict(value: Optional[str]) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _loads_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _active_assignment_filter(amo_id: str, active_on: Optional[date] = None):
    active_on = active_on or date.today()
    return (
        org_models.PositionAssignment.amo_id == amo_id,
        org_models.PositionAssignment.status.in_(ACTIVE_STATUSES),
        org_models.PositionAssignment.effective_from <= active_on,
        or_(
            org_models.PositionAssignment.effective_to.is_(None),
            org_models.PositionAssignment.effective_to >= active_on,
        ),
    )


def _active_engagement_filter(amo_id: str, active_on: Optional[date] = None):
    active_on = active_on or date.today()
    return (
        org_models.WorkforceEngagement.amo_id == amo_id,
        org_models.WorkforceEngagement.status == "ACTIVE",
        org_models.WorkforceEngagement.start_date <= active_on,
        or_(
            org_models.WorkforceEngagement.end_date.is_(None),
            org_models.WorkforceEngagement.end_date >= active_on,
        ),
    )


def _assert_unit_parent(db: Session, *, amo_id: str, unit_id: Optional[str], parent_id: Optional[str]) -> None:
    if not parent_id:
        return
    parent = db.query(org_models.OrganizationUnit).filter(
        org_models.OrganizationUnit.id == parent_id,
        org_models.OrganizationUnit.amo_id == amo_id,
    ).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent organization unit was not found in this AMO.")
    if unit_id and parent_id == unit_id:
        raise HTTPException(status_code=409, detail="An organization unit cannot be its own parent.")
    visited: set[str] = set()
    cursor = parent
    while cursor and cursor.parent_id:
        if str(cursor.id) in visited:
            raise HTTPException(status_code=409, detail="The existing organization hierarchy already contains a cycle.")
        visited.add(str(cursor.id))
        if unit_id and str(cursor.parent_id) == str(unit_id):
            raise HTTPException(status_code=409, detail="This parent change would create a circular organization hierarchy.")
        cursor = db.query(org_models.OrganizationUnit).filter(
            org_models.OrganizationUnit.id == cursor.parent_id,
            org_models.OrganizationUnit.amo_id == amo_id,
        ).first()


def _assert_position_parent(db: Session, *, amo_id: str, position_id: Optional[str], parent_id: Optional[str]) -> None:
    if not parent_id:
        return
    parent = db.query(org_models.OrganizationPosition).filter(
        org_models.OrganizationPosition.id == parent_id,
        org_models.OrganizationPosition.amo_id == amo_id,
    ).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Reporting position was not found in this AMO.")
    if position_id and str(position_id) == str(parent_id):
        raise HTTPException(status_code=409, detail="A position cannot report to itself.")
    visited: set[str] = set()
    cursor = parent
    while cursor and cursor.reports_to_position_id:
        if str(cursor.id) in visited:
            raise HTTPException(status_code=409, detail="The existing position hierarchy already contains a cycle.")
        visited.add(str(cursor.id))
        if position_id and str(cursor.reports_to_position_id) == str(position_id):
            raise HTTPException(status_code=409, detail="This reporting position would create a circular position hierarchy.")
        cursor = db.query(org_models.OrganizationPosition).filter(
            org_models.OrganizationPosition.id == cursor.reports_to_position_id,
            org_models.OrganizationPosition.amo_id == amo_id,
        ).first()


def _assert_manager_chain(db: Session, *, amo_id: str, user_id: str, manager_user_id: Optional[str]) -> None:
    if not manager_user_id:
        return
    if str(user_id) == str(manager_user_id):
        raise HTTPException(status_code=409, detail="A user cannot be their own reporting manager.")
    visited = {str(user_id)}
    cursor_id: Optional[str] = str(manager_user_id)
    while cursor_id:
        if cursor_id in visited:
            raise HTTPException(status_code=409, detail="This reporting manager would create a circular management chain.")
        visited.add(cursor_id)
        row = db.query(org_models.PositionAssignment).filter(
            *_active_assignment_filter(amo_id),
            org_models.PositionAssignment.user_id == cursor_id,
            org_models.PositionAssignment.is_primary.is_(True),
        ).order_by(org_models.PositionAssignment.effective_from.desc()).first()
        cursor_id = str(row.reporting_manager_user_id) if row and row.reporting_manager_user_id else None


def _user_names(db: Session, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    return {
        str(user.id): user.full_name
        for user in db.query(models.User).filter(models.User.id.in_(list(ids))).all()
    }


def _unit_read(db: Session, row: org_models.OrganizationUnit) -> org_schemas.OrganizationUnitRead:
    ids = {str(value) for value in (
        row.manager_user_id, row.deputy_manager_user_id, row.accountable_manager_user_id
    ) if value}
    names = _user_names(db, ids)
    parent = db.query(org_models.OrganizationUnit).filter(org_models.OrganizationUnit.id == row.parent_id).first() if row.parent_id else None
    position_count = int(db.query(func.count(org_models.OrganizationPosition.id)).filter(
        org_models.OrganizationPosition.unit_id == row.id,
        org_models.OrganizationPosition.is_active.is_(True),
    ).scalar() or 0)
    assignment_count = int(db.query(func.count(org_models.PositionAssignment.id)).join(
        org_models.OrganizationPosition,
        org_models.OrganizationPosition.id == org_models.PositionAssignment.position_id,
    ).filter(
        *_active_assignment_filter(str(row.amo_id)),
        org_models.OrganizationPosition.unit_id == row.id,
    ).scalar() or 0)
    return org_schemas.OrganizationUnitRead(
        id=str(row.id), amo_id=str(row.amo_id), code=row.code, name=row.name,
        unit_type=row.unit_type, parent_id=row.parent_id, parent_name=parent.name if parent else None,
        department_id=row.department_id, base_station_id=row.base_station_id, purpose=row.purpose,
        cost_center=row.cost_center, accountable_manager_user_id=row.accountable_manager_user_id,
        accountable_manager_name=names.get(str(row.accountable_manager_user_id)),
        manager_user_id=row.manager_user_id, manager_name=names.get(str(row.manager_user_id)),
        deputy_manager_user_id=row.deputy_manager_user_id, deputy_manager_name=names.get(str(row.deputy_manager_user_id)),
        quality_owner_user_id=row.quality_owner_user_id, headcount_limit=row.headcount_limit,
        sort_order=row.sort_order, effective_from=row.effective_from, effective_to=row.effective_to,
        is_active=bool(row.is_active), position_count=position_count, assignment_count=assignment_count,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _position_read(db: Session, row: org_models.OrganizationPosition) -> org_schemas.PositionRead:
    unit = db.query(org_models.OrganizationUnit).filter(org_models.OrganizationUnit.id == row.unit_id).first()
    parent = db.query(org_models.OrganizationPosition).filter(org_models.OrganizationPosition.id == row.reports_to_position_id).first() if row.reports_to_position_id else None
    occupied = int(db.query(func.count(org_models.PositionAssignment.id)).filter(
        *_active_assignment_filter(str(row.amo_id)),
        org_models.PositionAssignment.position_id == row.id,
    ).scalar() or 0)
    return org_schemas.PositionRead(
        id=str(row.id), amo_id=str(row.amo_id), unit_id=str(row.unit_id), unit_name=unit.name if unit else "Unknown unit",
        reports_to_position_id=row.reports_to_position_id,
        reports_to_position_title=parent.title if parent else None,
        code=row.code, title=row.title, job_family=row.job_family, grade=row.grade,
        employment_category=row.employment_category, headcount_limit=row.headcount_limit,
        is_supervisory=bool(row.is_supervisory), is_regulatory_post=bool(row.is_regulatory_post),
        regulatory_post_type=row.regulatory_post_type,
        authority_acceptance_required=bool(row.authority_acceptance_required),
        minimum_competence_summary=row.minimum_competence_summary,
        responsibilities=row.responsibilities, approval_scope=row.approval_scope,
        default_account_role=row.default_account_role, succession_criticality=row.succession_criticality,
        effective_from=row.effective_from, effective_to=row.effective_to, is_active=bool(row.is_active),
        occupied_count=occupied, vacancy_count=max(0, int(row.headcount_limit or 0) - occupied),
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _assignment_read(db: Session, row: org_models.PositionAssignment) -> org_schemas.PositionAssignmentRead:
    user = db.query(models.User).filter(models.User.id == row.user_id).first()
    manager = db.query(models.User).filter(models.User.id == row.reporting_manager_user_id).first() if row.reporting_manager_user_id else None
    position = db.query(org_models.OrganizationPosition).filter(org_models.OrganizationPosition.id == row.position_id).first()
    unit = db.query(org_models.OrganizationUnit).filter(org_models.OrganizationUnit.id == position.unit_id).first() if position else None
    return org_schemas.PositionAssignmentRead(
        id=str(row.id), amo_id=str(row.amo_id), user_id=str(row.user_id), user_name=user.full_name if user else "Unknown user",
        staff_code=user.staff_code if user else "", position_id=str(row.position_id),
        position_title=position.title if position else "Unknown position", unit_name=unit.name if unit else "Unknown unit",
        reporting_manager_user_id=row.reporting_manager_user_id,
        reporting_manager_name=manager.full_name if manager else None,
        assignment_type=row.assignment_type, status=row.status, is_primary=bool(row.is_primary),
        matrix_reporting=bool(row.matrix_reporting), matrix_reason=row.matrix_reason,
        fte_percent=Decimal(str(row.fte_percent or 100)), effective_from=row.effective_from,
        effective_to=row.effective_to, appointment_reference=row.appointment_reference,
        authority_acceptance_reference=row.authority_acceptance_reference,
        authority_accepted_on=row.authority_accepted_on, delegation_limitations=row.delegation_limitations,
        notes=row.notes, approved_by_user_id=row.approved_by_user_id, approved_at=row.approved_at,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _engagement_read(db: Session, row: org_models.WorkforceEngagement) -> org_schemas.WorkforceEngagementRead:
    user = db.query(models.User).filter(models.User.id == row.user_id).first()
    sponsor = db.query(models.User).filter(models.User.id == row.sponsor_user_id).first() if row.sponsor_user_id else None
    return org_schemas.WorkforceEngagementRead(
        id=str(row.id), amo_id=str(row.amo_id), user_id=str(row.user_id), user_name=user.full_name if user else "Unknown user",
        staff_code=user.staff_code if user else "", engagement_type=row.engagement_type, status=row.status,
        contract_reference=row.contract_reference, start_date=row.start_date, end_date=row.end_date,
        probation_months=row.probation_months, sponsor_user_id=row.sponsor_user_id,
        sponsor_name=sponsor.full_name if sponsor else None, external_organisation=row.external_organisation,
        institution_or_vendor=row.institution_or_vendor, programme_name=row.programme_name,
        learning_objectives=row.learning_objectives, work_permit_status=row.work_permit_status,
        work_permit_reference=row.work_permit_reference, work_permit_expires_on=row.work_permit_expires_on,
        background_check_status=row.background_check_status, access_expiry_on=row.access_expiry_on,
        offboarding_required=bool(row.offboarding_required), notes=row.notes,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _policy_read(db: Session, row: org_models.GroupPolicy) -> org_schemas.GroupPolicyRead:
    group = db.query(models.UserGroup).filter(models.UserGroup.id == row.group_id).first()
    unit = db.query(org_models.OrganizationUnit).filter(org_models.OrganizationUnit.id == row.unit_id).first() if row.unit_id else None
    return org_schemas.GroupPolicyRead(
        id=str(row.id), amo_id=str(row.amo_id), group_id=str(row.group_id), group_name=group.name if group else "Unknown group",
        unit_id=row.unit_id, unit_name=unit.name if unit else None, code=row.code, name=row.name,
        description=row.description, inheritance_mode=row.inheritance_mode, membership_mode=row.membership_mode,
        default_account_role=row.default_account_role, permission_template=_loads_dict(row.permission_template_json),
        segregation_tags=_loads_list(row.segregation_tags_json),
        requires_manager_approval=bool(row.requires_manager_approval),
        requires_quality_approval=bool(row.requires_quality_approval),
        maximum_assignment_days=row.maximum_assignment_days, effective_from=row.effective_from,
        effective_to=row.effective_to, is_active=bool(row.is_active), created_at=row.created_at, updated_at=row.updated_at,
    )


def _compliance_read(row: org_models.PersonnelComplianceProfile) -> org_schemas.ComplianceProfileRead:
    return org_schemas.ComplianceProfileRead(
        id=str(row.id), amo_id=str(row.amo_id), user_id=str(row.user_id), legal_name=row.legal_name,
        preferred_name=row.preferred_name, nationality=row.nationality, residence_country=row.residence_country,
        identity_verified=bool(row.identity_verified), identity_reference=row.identity_reference,
        identity_verified_at=row.identity_verified_at, identity_verified_by_user_id=row.identity_verified_by_user_id,
        emergency_contact_name=row.emergency_contact_name,
        emergency_contact_relationship=row.emergency_contact_relationship,
        emergency_contact_phone=row.emergency_contact_phone, data_classification=row.data_classification,
        retention_class=row.retention_class, confidentiality_ack_at=row.confidentiality_ack_at,
        code_of_conduct_ack_at=row.code_of_conduct_ack_at, conflict_declaration_at=row.conflict_declaration_at,
        competence_status=row.competence_status, training_status=row.training_status,
        authorisation_status=row.authorisation_status, medical_fitness_status=row.medical_fitness_status,
        last_competence_assessment_on=row.last_competence_assessment_on, next_review_on=row.next_review_on,
        compliance_owner_user_id=row.compliance_owner_user_id, restrictions=row.restrictions, notes=row.notes,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _credential_read(row: org_models.PersonnelCredential) -> org_schemas.PersonnelCredentialRead:
    return org_schemas.PersonnelCredentialRead(
        id=str(row.id), amo_id=str(row.amo_id), user_id=str(row.user_id), credential_type=row.credential_type,
        authority=row.authority, reference=row.reference, title=row.title, scope=_loads_dict(row.scope_json),
        issued_on=row.issued_on, expires_on=row.expires_on, status=row.status,
        evidence_document_id=row.evidence_document_id, restrictions=row.restrictions,
        verified_by_user_id=row.verified_by_user_id, verified_at=row.verified_at,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _readiness(profile: Optional[org_models.PersonnelComplianceProfile], assignment, engagement, credentials) -> tuple[int, list[str]]:
    checks: list[tuple[bool, str]] = [
        (assignment is not None, "No active primary position assignment"),
        (engagement is not None, "No active employment or contingent engagement"),
        (profile is not None and bool(profile.identity_verified), "Identity has not been verified"),
        (profile is not None and profile.competence_status in {"CURRENT", "VALID"}, "Competence assessment is not current"),
        (profile is not None and profile.training_status in {"CURRENT", "VALID"}, "Required training is not current"),
        (profile is not None and bool(profile.code_of_conduct_ack_at), "Code of conduct acknowledgement is missing"),
    ]
    if assignment:
        position = getattr(assignment, "_position_cache", None)
        if position and position.is_regulatory_post:
            checks.append((bool(assignment.appointment_reference), "Regulatory appointment reference is missing"))
            if position.authority_acceptance_required:
                checks.append((bool(assignment.authority_acceptance_reference), "Authority acceptance evidence is missing"))
    today = date.today()
    expired = [item for item in credentials if item.expires_on and item.expires_on < today and item.status == "VALID"]
    checks.append((not expired, "One or more credentials are expired"))
    passed = sum(1 for ok, _ in checks if ok)
    return round((passed / len(checks)) * 100) if checks else 100, [message for ok, message in checks if not ok]


@router.get("/organization/overview", response_model=org_schemas.OrganizationOverviewRead)
def organization_overview(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    target = _target_amo_id(current_user, amo_id)
    today = date.today()
    units = int(db.query(func.count(org_models.OrganizationUnit.id)).filter(org_models.OrganizationUnit.amo_id == target).scalar() or 0)
    active_units = int(db.query(func.count(org_models.OrganizationUnit.id)).filter(org_models.OrganizationUnit.amo_id == target, org_models.OrganizationUnit.is_active.is_(True)).scalar() or 0)
    positions = db.query(org_models.OrganizationPosition).filter(org_models.OrganizationPosition.amo_id == target, org_models.OrganizationPosition.is_active.is_(True)).all()
    approved_headcount = sum(int(row.headcount_limit or 0) for row in positions)
    active_assignments = int(db.query(func.count(org_models.PositionAssignment.id)).filter(*_active_assignment_filter(target, today)).scalar() or 0)
    workforce_engagements = int(db.query(func.count(org_models.WorkforceEngagement.id)).filter(*_active_engagement_filter(target, today)).scalar() or 0)
    contingent_workers = int(db.query(func.count(org_models.WorkforceEngagement.id)).filter(*_active_engagement_filter(target, today), org_models.WorkforceEngagement.engagement_type.in_(CONTINGENT_TYPES)).scalar() or 0)
    active_users = db.query(models.User).filter(models.User.amo_id == target, models.User.is_active.is_(True))
    assigned_user_ids = db.query(org_models.PositionAssignment.user_id).filter(*_active_assignment_filter(target, today), org_models.PositionAssignment.is_primary.is_(True))
    engaged_user_ids = db.query(org_models.WorkforceEngagement.user_id).filter(*_active_engagement_filter(target, today))
    due_profiles = int(db.query(func.count(org_models.PersonnelComplianceProfile.id)).filter(
        org_models.PersonnelComplianceProfile.amo_id == target,
        or_(org_models.PersonnelComplianceProfile.next_review_on.is_(None), org_models.PersonnelComplianceProfile.next_review_on <= today),
    ).scalar() or 0)
    expiring = int(db.query(func.count(org_models.PersonnelCredential.id)).filter(
        org_models.PersonnelCredential.amo_id == target,
        org_models.PersonnelCredential.status == "VALID",
        org_models.PersonnelCredential.expires_on >= today,
        org_models.PersonnelCredential.expires_on <= today + timedelta(days=90),
    ).scalar() or 0)
    return org_schemas.OrganizationOverviewRead(
        units=units, active_units=active_units, positions=len(positions), approved_headcount=approved_headcount,
        active_assignments=active_assignments, vacant_positions=max(0, approved_headcount - active_assignments),
        workforce_engagements=workforce_engagements, contingent_workers=contingent_workers,
        missing_primary_assignment=int(active_users.filter(~models.User.id.in_(assigned_user_ids)).count()),
        missing_engagement=int(active_users.filter(~models.User.id.in_(engaged_user_ids)).count()),
        compliance_profiles_due=due_profiles, expiring_credentials_90_days=expiring,
    )


@router.get("/organization/units", response_model=list[org_schemas.OrganizationUnitRead])
def list_units(amo_id: Optional[str] = None, include_inactive: bool = False, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, amo_id)
    query = db.query(org_models.OrganizationUnit).filter(org_models.OrganizationUnit.amo_id == target)
    if not include_inactive:
        query = query.filter(org_models.OrganizationUnit.is_active.is_(True))
    return [_unit_read(db, row) for row in query.order_by(org_models.OrganizationUnit.sort_order, org_models.OrganizationUnit.name).all()]


@router.post("/organization/units", response_model=org_schemas.OrganizationUnitRead, status_code=status.HTTP_201_CREATED)
def create_unit(payload: org_schemas.OrganizationUnitCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, payload.amo_id)
    unit_type = payload.unit_type.strip().upper()
    if unit_type not in UNIT_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported organization unit type: {unit_type}.")
    _date_order(payload.effective_from, payload.effective_to, "Organization unit")
    _assert_unit_parent(db, amo_id=target, unit_id=None, parent_id=payload.parent_id)
    for user_id in (payload.accountable_manager_user_id, payload.manager_user_id, payload.deputy_manager_user_id, payload.quality_owner_user_id):
        _tenant_user(db, amo_id=target, user_id=user_id, active_required=bool(user_id))
    row = org_models.OrganizationUnit(
        amo_id=target, code=_normalise_code(payload.code), name=payload.name.strip(), unit_type=unit_type,
        parent_id=payload.parent_id, department_id=payload.department_id, base_station_id=payload.base_station_id,
        purpose=payload.purpose, cost_center=payload.cost_center,
        accountable_manager_user_id=payload.accountable_manager_user_id, manager_user_id=payload.manager_user_id,
        deputy_manager_user_id=payload.deputy_manager_user_id, quality_owner_user_id=payload.quality_owner_user_id,
        headcount_limit=payload.headcount_limit, sort_order=payload.sort_order,
        effective_from=payload.effective_from, effective_to=payload.effective_to,
        is_active=payload.is_active, created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    audit_services.log_event(db, amo_id=target, actor_user_id=str(current_user.id), entity_type="accounts.organization_unit", entity_id=str(row.id), action="CREATED", after={"code": row.code, "name": row.name, "unit_type": row.unit_type}, metadata={"module": "accounts", "source": "corporate_structure"})
    db.commit(); db.refresh(row)
    return _unit_read(db, row)


@router.patch("/organization/units/{unit_id}", response_model=org_schemas.OrganizationUnitRead)
def update_unit(unit_id: str, payload: org_schemas.OrganizationUnitUpdate, amo_id: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, amo_id)
    row = db.query(org_models.OrganizationUnit).filter(org_models.OrganizationUnit.id == unit_id, org_models.OrganizationUnit.amo_id == target).first()
    if not row:
        raise HTTPException(status_code=404, detail="Organization unit not found.")
    changes = payload.model_dump(exclude_unset=True)
    if "parent_id" in changes:
        _assert_unit_parent(db, amo_id=target, unit_id=str(row.id), parent_id=changes["parent_id"])
    if "unit_type" in changes:
        changes["unit_type"] = str(changes["unit_type"]).strip().upper()
        if changes["unit_type"] not in UNIT_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported organization unit type.")
    for field in ("accountable_manager_user_id", "manager_user_id", "deputy_manager_user_id", "quality_owner_user_id"):
        if field in changes and changes[field]:
            _tenant_user(db, amo_id=target, user_id=changes[field], active_required=True)
    effective_from = changes.get("effective_from", row.effective_from)
    effective_to = changes.get("effective_to", row.effective_to)
    _date_order(effective_from, effective_to, "Organization unit")
    before = {key: getattr(row, key) for key in changes}
    for key, value in changes.items():
        setattr(row, key, value)
    audit_services.log_event(db, amo_id=target, actor_user_id=str(current_user.id), entity_type="accounts.organization_unit", entity_id=str(row.id), action="UPDATED", before=before, after=changes, metadata={"module": "accounts", "source": "corporate_structure"})
    db.commit(); db.refresh(row)
    return _unit_read(db, row)


@router.get("/organization/positions", response_model=list[org_schemas.PositionRead])
def list_positions(amo_id: Optional[str] = None, unit_id: Optional[str] = None, include_inactive: bool = False, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, amo_id)
    query = db.query(org_models.OrganizationPosition).filter(org_models.OrganizationPosition.amo_id == target)
    if unit_id:
        query = query.filter(org_models.OrganizationPosition.unit_id == unit_id)
    if not include_inactive:
        query = query.filter(org_models.OrganizationPosition.is_active.is_(True))
    return [_position_read(db, row) for row in query.order_by(org_models.OrganizationPosition.title).all()]


@router.post("/organization/positions", response_model=org_schemas.PositionRead, status_code=status.HTTP_201_CREATED)
def create_position(payload: org_schemas.PositionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, payload.amo_id)
    unit = db.query(org_models.OrganizationUnit).filter(org_models.OrganizationUnit.id == payload.unit_id, org_models.OrganizationUnit.amo_id == target, org_models.OrganizationUnit.is_active.is_(True)).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Active organization unit not found.")
    _assert_position_parent(db, amo_id=target, position_id=None, parent_id=payload.reports_to_position_id)
    _date_order(payload.effective_from, payload.effective_to, "Position")
    if payload.is_regulatory_post and not payload.regulatory_post_type:
        raise HTTPException(status_code=422, detail="Regulatory post type is required for a regulatory position.")
    row = org_models.OrganizationPosition(
        amo_id=target, unit_id=payload.unit_id, reports_to_position_id=payload.reports_to_position_id,
        code=_normalise_code(payload.code), title=payload.title.strip(), job_family=payload.job_family,
        grade=payload.grade, employment_category=payload.employment_category.strip().upper(),
        headcount_limit=payload.headcount_limit, is_supervisory=payload.is_supervisory,
        is_regulatory_post=payload.is_regulatory_post, regulatory_post_type=payload.regulatory_post_type,
        authority_acceptance_required=payload.authority_acceptance_required,
        minimum_competence_summary=payload.minimum_competence_summary,
        responsibilities=payload.responsibilities, approval_scope=payload.approval_scope,
        default_account_role=payload.default_account_role, succession_criticality=payload.succession_criticality,
        effective_from=payload.effective_from, effective_to=payload.effective_to,
        is_active=payload.is_active, created_by_user_id=current_user.id,
    )
    db.add(row); db.flush()
    audit_services.log_event(db, amo_id=target, actor_user_id=str(current_user.id), entity_type="accounts.organization_position", entity_id=str(row.id), action="CREATED", after={"code": row.code, "title": row.title, "unit_id": row.unit_id}, metadata={"module": "accounts", "source": "corporate_structure"})
    db.commit(); db.refresh(row)
    return _position_read(db, row)


@router.get("/organization/assignments", response_model=list[org_schemas.PositionAssignmentRead])
def list_assignments(amo_id: Optional[str] = None, user_id: Optional[str] = None, active_only: bool = True, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, amo_id)
    query = db.query(org_models.PositionAssignment).filter(org_models.PositionAssignment.amo_id == target)
    if user_id:
        query = query.filter(org_models.PositionAssignment.user_id == user_id)
    if active_only:
        query = query.filter(*_active_assignment_filter(target))
    return [_assignment_read(db, row) for row in query.order_by(org_models.PositionAssignment.effective_from.desc()).all()]


@router.post("/organization/assignments", response_model=org_schemas.PositionAssignmentRead, status_code=status.HTTP_201_CREATED)
def create_assignment(payload: org_schemas.PositionAssignmentCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, payload.amo_id)
    user = _tenant_user(db, amo_id=target, user_id=payload.user_id, active_required=True)
    manager = _tenant_user(db, amo_id=target, user_id=payload.reporting_manager_user_id, active_required=bool(payload.reporting_manager_user_id))
    position = db.query(org_models.OrganizationPosition).filter(org_models.OrganizationPosition.id == payload.position_id, org_models.OrganizationPosition.amo_id == target, org_models.OrganizationPosition.is_active.is_(True)).first()
    if not position:
        raise HTTPException(status_code=404, detail="Active position not found.")
    assignment_type = payload.assignment_type.strip().upper()
    if assignment_type not in ASSIGNMENT_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported assignment type: {assignment_type}.")
    _date_order(payload.effective_from, payload.effective_to, "Assignment")
    _assert_manager_chain(db, amo_id=target, user_id=str(user.id), manager_user_id=str(manager.id) if manager else None)
    if payload.is_primary and payload.status in ACTIVE_STATUSES:
        existing = db.query(org_models.PositionAssignment).filter(
            *_active_assignment_filter(target, payload.effective_from),
            org_models.PositionAssignment.user_id == user.id,
            org_models.PositionAssignment.is_primary.is_(True),
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="The user already has an active primary position assignment. End or change it before creating another.")
    occupied = int(db.query(func.count(org_models.PositionAssignment.id)).filter(
        *_active_assignment_filter(target, payload.effective_from),
        org_models.PositionAssignment.position_id == position.id,
    ).scalar() or 0)
    if occupied >= int(position.headcount_limit or 1):
        raise HTTPException(status_code=409, detail="The approved headcount for this position is already filled.")
    if position.is_regulatory_post and not payload.appointment_reference:
        raise HTTPException(status_code=422, detail="An appointment reference is required for a regulatory post.")
    if position.authority_acceptance_required and not payload.authority_acceptance_reference:
        raise HTTPException(status_code=422, detail="Authority acceptance evidence is required for this position.")
    row = org_models.PositionAssignment(
        amo_id=target, user_id=user.id, position_id=position.id,
        reporting_manager_user_id=manager.id if manager else None, assignment_type=assignment_type,
        status=payload.status.strip().upper(), is_primary=payload.is_primary,
        matrix_reporting=payload.matrix_reporting, matrix_reason=payload.matrix_reason,
        fte_percent=payload.fte_percent, effective_from=payload.effective_from,
        effective_to=payload.effective_to, appointment_reference=payload.appointment_reference,
        authority_acceptance_reference=payload.authority_acceptance_reference,
        authority_accepted_on=payload.authority_accepted_on,
        delegation_limitations=payload.delegation_limitations, notes=payload.notes,
        created_by_user_id=current_user.id, approved_by_user_id=current_user.id,
        approved_at=datetime.now(timezone.utc),
    )
    db.add(row); db.flush()
    if payload.is_primary:
        user.position_title = position.title
        db.add(user)
    audit_services.log_event(db, amo_id=target, actor_user_id=str(current_user.id), entity_type="accounts.position_assignment", entity_id=str(row.id), action="CREATED", after={"user_id": str(user.id), "position_id": str(position.id), "assignment_type": row.assignment_type}, metadata={"module": "accounts", "source": "corporate_structure"})
    db.commit(); db.refresh(row)
    return _assignment_read(db, row)


@router.get("/organization/engagements", response_model=list[org_schemas.WorkforceEngagementRead])
def list_engagements(amo_id: Optional[str] = None, user_id: Optional[str] = None, active_only: bool = True, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, amo_id)
    query = db.query(org_models.WorkforceEngagement).filter(org_models.WorkforceEngagement.amo_id == target)
    if user_id:
        query = query.filter(org_models.WorkforceEngagement.user_id == user_id)
    if active_only:
        query = query.filter(*_active_engagement_filter(target))
    return [_engagement_read(db, row) for row in query.order_by(org_models.WorkforceEngagement.start_date.desc()).all()]


@router.post("/organization/engagements", response_model=org_schemas.WorkforceEngagementRead, status_code=status.HTTP_201_CREATED)
def create_engagement(payload: org_schemas.WorkforceEngagementCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, payload.amo_id)
    user = _tenant_user(db, amo_id=target, user_id=payload.user_id, active_required=True)
    engagement_type = payload.engagement_type.strip().upper()
    if engagement_type not in ENGAGEMENT_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported engagement type: {engagement_type}.")
    _date_order(payload.start_date, payload.end_date, "Engagement")
    if engagement_type in TIME_BOUND_ENGAGEMENTS and not payload.end_date:
        raise HTTPException(status_code=422, detail=f"An end date is required for {engagement_type.lower()} engagements.")
    sponsor = _tenant_user(db, amo_id=target, user_id=payload.sponsor_user_id, active_required=bool(payload.sponsor_user_id))
    if engagement_type in SPONSOR_REQUIRED_ENGAGEMENTS and not sponsor:
        raise HTTPException(status_code=422, detail=f"A responsible internal sponsor is required for {engagement_type.lower()} personnel.")
    existing = db.query(org_models.WorkforceEngagement).filter(
        *_active_engagement_filter(target, payload.start_date),
        org_models.WorkforceEngagement.user_id == user.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="The user already has an active workforce engagement.")
    access_expiry = payload.access_expiry_on or (payload.end_date if engagement_type in TIME_BOUND_ENGAGEMENTS else None)
    row = org_models.WorkforceEngagement(
        amo_id=target, user_id=user.id, engagement_type=engagement_type,
        status=payload.status.strip().upper(), contract_reference=payload.contract_reference,
        start_date=payload.start_date, end_date=payload.end_date, probation_months=payload.probation_months,
        sponsor_user_id=sponsor.id if sponsor else None, external_organisation=payload.external_organisation,
        institution_or_vendor=payload.institution_or_vendor, programme_name=payload.programme_name,
        learning_objectives=payload.learning_objectives, work_permit_status=payload.work_permit_status,
        work_permit_reference=payload.work_permit_reference, work_permit_expires_on=payload.work_permit_expires_on,
        background_check_status=payload.background_check_status, access_expiry_on=access_expiry,
        offboarding_required=payload.offboarding_required, notes=payload.notes,
        created_by_user_id=current_user.id,
    )
    db.add(row); db.flush()
    audit_services.log_event(db, amo_id=target, actor_user_id=str(current_user.id), entity_type="accounts.workforce_engagement", entity_id=str(row.id), action="CREATED", after={"user_id": str(user.id), "engagement_type": engagement_type, "end_date": str(payload.end_date) if payload.end_date else None}, metadata={"module": "accounts", "source": "corporate_structure"})
    db.commit(); db.refresh(row)
    return _engagement_read(db, row)


@router.get("/organization/group-policies", response_model=list[org_schemas.GroupPolicyRead])
def list_group_policies(amo_id: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, amo_id)
    return [_policy_read(db, row) for row in db.query(org_models.GroupPolicy).filter(org_models.GroupPolicy.amo_id == target).order_by(org_models.GroupPolicy.name).all()]


@router.post("/organization/group-policies", response_model=org_schemas.GroupPolicyRead, status_code=status.HTTP_201_CREATED)
def create_group_policy(payload: org_schemas.GroupPolicyCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, payload.amo_id)
    group = db.query(models.UserGroup).filter(models.UserGroup.id == payload.group_id, models.UserGroup.amo_id == target, models.UserGroup.is_active.is_(True)).first()
    if not group:
        raise HTTPException(status_code=404, detail="Active user group not found.")
    if payload.unit_id:
        unit = db.query(org_models.OrganizationUnit).filter(org_models.OrganizationUnit.id == payload.unit_id, org_models.OrganizationUnit.amo_id == target, org_models.OrganizationUnit.is_active.is_(True)).first()
        if not unit:
            raise HTTPException(status_code=404, detail="Active organization unit not found.")
    _date_order(payload.effective_from, payload.effective_to, "Group policy")
    row = org_models.GroupPolicy(
        amo_id=target, group_id=payload.group_id, unit_id=payload.unit_id,
        code=_normalise_code(payload.code), name=payload.name.strip(), description=payload.description,
        inheritance_mode=payload.inheritance_mode.strip().upper(), membership_mode=payload.membership_mode.strip().upper(),
        default_account_role=payload.default_account_role,
        permission_template_json=json.dumps(payload.permission_template, sort_keys=True),
        segregation_tags_json=json.dumps(sorted(set(payload.segregation_tags))),
        requires_manager_approval=payload.requires_manager_approval,
        requires_quality_approval=payload.requires_quality_approval,
        maximum_assignment_days=payload.maximum_assignment_days,
        effective_from=payload.effective_from, effective_to=payload.effective_to,
        is_active=payload.is_active, created_by_user_id=current_user.id,
    )
    db.add(row); db.flush()
    audit_services.log_event(db, amo_id=target, actor_user_id=str(current_user.id), entity_type="accounts.group_policy", entity_id=str(row.id), action="CREATED", after={"group_id": str(group.id), "code": row.code, "unit_id": row.unit_id}, metadata={"module": "accounts", "source": "corporate_structure"})
    db.commit(); db.refresh(row)
    return _policy_read(db, row)


@router.get("/organization/users/{user_id}/governance", response_model=org_schemas.UserGovernanceRead)
def get_user_governance(user_id: str, amo_id: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, amo_id)
    user = _tenant_user(db, amo_id=target, user_id=user_id)
    assignments = db.query(org_models.PositionAssignment).filter(org_models.PositionAssignment.amo_id == target, org_models.PositionAssignment.user_id == user.id).order_by(org_models.PositionAssignment.effective_from.desc()).all()
    engagements = db.query(org_models.WorkforceEngagement).filter(org_models.WorkforceEngagement.amo_id == target, org_models.WorkforceEngagement.user_id == user.id).order_by(org_models.WorkforceEngagement.start_date.desc()).all()
    profile = db.query(org_models.PersonnelComplianceProfile).filter(org_models.PersonnelComplianceProfile.amo_id == target, org_models.PersonnelComplianceProfile.user_id == user.id).first()
    credentials = db.query(org_models.PersonnelCredential).filter(org_models.PersonnelCredential.amo_id == target, org_models.PersonnelCredential.user_id == user.id).order_by(org_models.PersonnelCredential.expires_on.asc().nullslast()).all()
    primary = next((row for row in assignments if row.is_primary and row.status in ACTIVE_STATUSES and row.effective_from <= date.today() and (row.effective_to is None or row.effective_to >= date.today())), None)
    engagement = next((row for row in engagements if row.status == "ACTIVE" and row.start_date <= date.today() and (row.end_date is None or row.end_date >= date.today())), None)
    if primary:
        primary._position_cache = db.query(org_models.OrganizationPosition).filter(org_models.OrganizationPosition.id == primary.position_id).first()
    score, gaps = _readiness(profile, primary, engagement, credentials)
    return org_schemas.UserGovernanceRead(
        user={"id": str(user.id), "full_name": user.full_name, "staff_code": user.staff_code, "email": user.email, "position_title": user.position_title, "is_active": bool(user.is_active), "role": str(getattr(user.role, "value", user.role))},
        primary_assignment=_assignment_read(db, primary) if primary else None,
        assignments=[_assignment_read(db, row) for row in assignments],
        active_engagement=_engagement_read(db, engagement) if engagement else None,
        engagements=[_engagement_read(db, row) for row in engagements],
        compliance_profile=_compliance_read(profile) if profile else None,
        credentials=[_credential_read(row) for row in credentials], readiness_score=score, readiness_gaps=gaps,
    )


@router.put("/organization/users/{user_id}/compliance-profile", response_model=org_schemas.ComplianceProfileRead)
def upsert_compliance_profile(user_id: str, payload: org_schemas.ComplianceProfileUpdate, amo_id: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, amo_id)
    user = _tenant_user(db, amo_id=target, user_id=user_id)
    row = db.query(org_models.PersonnelComplianceProfile).filter(org_models.PersonnelComplianceProfile.amo_id == target, org_models.PersonnelComplianceProfile.user_id == user.id).first()
    created = row is None
    if row is None:
        row = org_models.PersonnelComplianceProfile(amo_id=target, user_id=user.id)
    values = payload.model_dump()
    for key, value in values.items():
        setattr(row, key, value)
    if payload.identity_verified and not row.identity_verified_at:
        row.identity_verified_at = datetime.now(timezone.utc)
        row.identity_verified_by_user_id = current_user.id
    if not payload.identity_verified:
        row.identity_verified_at = None
        row.identity_verified_by_user_id = None
    db.add(row); db.flush()
    audit_services.log_event(db, amo_id=target, actor_user_id=str(current_user.id), entity_type="accounts.personnel_compliance_profile", entity_id=str(row.id), action="CREATED" if created else "UPDATED", after={"user_id": str(user.id), "identity_verified": bool(row.identity_verified), "competence_status": row.competence_status, "training_status": row.training_status, "next_review_on": str(row.next_review_on) if row.next_review_on else None}, metadata={"module": "accounts", "source": "personnel_governance"})
    db.commit(); db.refresh(row)
    return _compliance_read(row)


@router.post("/organization/credentials", response_model=org_schemas.PersonnelCredentialRead, status_code=status.HTTP_201_CREATED)
def create_credential(payload: org_schemas.PersonnelCredentialCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    target = _target_amo_id(current_user, payload.amo_id)
    user = _tenant_user(db, amo_id=target, user_id=payload.user_id)
    _date_order(payload.issued_on, payload.expires_on, "Credential")
    row = org_models.PersonnelCredential(
        amo_id=target, user_id=user.id, credential_type=payload.credential_type.strip().upper(),
        authority=payload.authority, reference=payload.reference.strip(), title=payload.title,
        scope_json=json.dumps(payload.scope, sort_keys=True), issued_on=payload.issued_on,
        expires_on=payload.expires_on, status=payload.status.strip().upper(),
        evidence_document_id=payload.evidence_document_id, restrictions=payload.restrictions,
        verified_by_user_id=current_user.id, verified_at=datetime.now(timezone.utc),
    )
    db.add(row); db.flush()
    audit_services.log_event(db, amo_id=target, actor_user_id=str(current_user.id), entity_type="accounts.personnel_credential", entity_id=str(row.id), action="CREATED", after={"user_id": str(user.id), "credential_type": row.credential_type, "reference": row.reference, "expires_on": str(row.expires_on) if row.expires_on else None}, metadata={"module": "accounts", "source": "personnel_governance"})
    db.commit(); db.refresh(row)
    return _credential_read(row)


@portal_router.get("/my-profile", response_model=org_schemas.MyProfileRead)
def my_governance_profile(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    target = str(current_user.amo_id)
    assignment = db.query(org_models.PositionAssignment).filter(*_active_assignment_filter(target), org_models.PositionAssignment.user_id == current_user.id, org_models.PositionAssignment.is_primary.is_(True)).order_by(org_models.PositionAssignment.effective_from.desc()).first()
    engagement = db.query(org_models.WorkforceEngagement).filter(*_active_engagement_filter(target), org_models.WorkforceEngagement.user_id == current_user.id).order_by(org_models.WorkforceEngagement.start_date.desc()).first()
    profile = db.query(org_models.PersonnelComplianceProfile).filter(org_models.PersonnelComplianceProfile.amo_id == target, org_models.PersonnelComplianceProfile.user_id == current_user.id).first()
    credentials = db.query(org_models.PersonnelCredential).filter(org_models.PersonnelCredential.amo_id == target, org_models.PersonnelCredential.user_id == current_user.id).order_by(org_models.PersonnelCredential.expires_on.asc().nullslast()).all()
    return org_schemas.MyProfileRead(
        user={"id": str(current_user.id), "full_name": current_user.full_name, "staff_code": current_user.staff_code, "email": current_user.email, "position_title": current_user.position_title, "role": str(getattr(current_user.role, "value", current_user.role))},
        assignment=_assignment_read(db, assignment) if assignment else None,
        engagement=_engagement_read(db, engagement) if engagement else None,
        compliance_profile=_compliance_read(profile) if profile else None,
        credentials=[_credential_read(row) for row in credentials],
    )


@portal_router.get("/my-team", response_model=list[org_schemas.ManagerTeamMemberRead])
def my_team(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    target = str(current_user.amo_id)
    assignments = db.query(org_models.PositionAssignment).filter(
        *_active_assignment_filter(target),
        org_models.PositionAssignment.reporting_manager_user_id == current_user.id,
    ).order_by(org_models.PositionAssignment.is_primary.desc(), org_models.PositionAssignment.effective_from.desc()).all()
    result = []
    seen: set[str] = set()
    for assignment in assignments:
        user_id = str(assignment.user_id)
        if user_id in seen:
            continue
        seen.add(user_id)
        user = db.query(models.User).filter(models.User.id == assignment.user_id, models.User.amo_id == target).first()
        if not user:
            continue
        position = db.query(org_models.OrganizationPosition).filter(org_models.OrganizationPosition.id == assignment.position_id).first()
        unit = db.query(org_models.OrganizationUnit).filter(org_models.OrganizationUnit.id == position.unit_id).first() if position else None
        engagement = db.query(org_models.WorkforceEngagement).filter(*_active_engagement_filter(target), org_models.WorkforceEngagement.user_id == user.id).first()
        profile = db.query(org_models.PersonnelComplianceProfile).filter(org_models.PersonnelComplianceProfile.amo_id == target, org_models.PersonnelComplianceProfile.user_id == user.id).first()
        credentials = db.query(org_models.PersonnelCredential).filter(org_models.PersonnelCredential.amo_id == target, org_models.PersonnelCredential.user_id == user.id).all()
        assignment._position_cache = position
        score, gaps = _readiness(profile, assignment, engagement, credentials)
        expiring = sum(1 for item in credentials if item.status == "VALID" and item.expires_on and date.today() <= item.expires_on <= date.today() + timedelta(days=90))
        result.append(org_schemas.ManagerTeamMemberRead(
            user_id=user_id, full_name=user.full_name, staff_code=user.staff_code, email=user.email,
            position_title=position.title if position else (user.position_title or "Unassigned"),
            unit_name=unit.name if unit else "Unassigned", engagement_type=engagement.engagement_type if engagement else None,
            engagement_end_date=engagement.end_date if engagement else None,
            competence_status=profile.competence_status if profile else "NOT_ASSESSED",
            training_status=profile.training_status if profile else "NOT_ASSESSED",
            expiring_credentials=expiring, readiness_score=score, readiness_gaps=gaps,
        ))
    return result
