"""Governed Workforce hierarchy, positions, directory and supervisor endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..audit import services as audit_services
from . import governance_directory, governance_schemas, hierarchy_roles, permissions, services

router = APIRouter(prefix="/workforce/hr", tags=["workforce-governance"])


def _amo(user: account_models.User) -> str:
    return services.effective_amo_id(user)


def _error(detail: str, *, code: str, status_code: int = status.HTTP_400_BAD_REQUEST):
    return HTTPException(status_code=status_code, detail={
        "detail": detail, "error_code": code, "field_errors": {}, "conflicts": [], "retryable": False,
    })


def _view(db: Session, user: account_models.User):
    permissions.require_permission(db, user=user, permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE)


def _manage(db: Session, user: account_models.User):
    permissions.require_permission(db, user=user, permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS)


def _filters(**values):
    try:
        return governance_schemas.GovernedPeopleFilterInput(**values)
    except ValueError as exc:
        raise _error("One or more governed Workforce filters are invalid.", code="WORKFORCE_GOVERNED_FILTER_INVALID") from exc


@router.get("/people/governed", response_model=governance_schemas.GovernedPeoplePage)
def governed_people(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=250),
    search: str | None = Query(default=None, max_length=200),
    department_id: str | None = None,
    role: str | None = None,
    position_title: str | None = Query(default=None, max_length=255),
    contract_type: str | None = None,
    employment_status: str | None = None,
    base_station_id: str | None = None,
    group_id: str | None = None,
    readiness_state: str | None = None,
    contract_state: str | None = None,
    pattern_state: str | None = None,
    expires_within_days: int | None = Query(default=None, ge=1, le=365),
    org_unit_id: str | None = None,
    include_descendants: bool = True,
    placement_type: str | None = None,
    position_id: str | None = None,
    job_family_id: str | None = None,
    grade_id: str | None = None,
    supervisor_user_id: str | None = None,
    secondary_base_station_id: str | None = None,
    contract_effective_from_on_or_after: date | None = None,
    contract_effective_from_on_or_before: date | None = None,
    contract_effective_to_on_or_after: date | None = None,
    contract_effective_to_on_or_before: date | None = None,
    lifecycle_state: str | None = None,
    sort_by: str = "name",
    sort_dir: str = "asc",
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _view(db, current_user)
    filters = _filters(
        search=search, department_id=department_id, role=role, position_title=position_title,
        contract_type=contract_type, employment_status=employment_status, base_station_id=base_station_id,
        group_id=group_id, readiness_state=readiness_state, contract_state=contract_state,
        pattern_state=pattern_state, expires_within_days=expires_within_days,
        org_unit_id=org_unit_id, include_descendants=include_descendants, placement_type=placement_type,
        position_id=position_id, job_family_id=job_family_id, grade_id=grade_id,
        supervisor_user_id=supervisor_user_id, secondary_base_station_id=secondary_base_station_id,
        contract_effective_from_on_or_after=contract_effective_from_on_or_after,
        contract_effective_from_on_or_before=contract_effective_from_on_or_before,
        contract_effective_to_on_or_after=contract_effective_to_on_or_after,
        contract_effective_to_on_or_before=contract_effective_to_on_or_before,
        lifecycle_state=lifecycle_state, sort_by=sort_by, sort_dir=sort_dir,
    )
    try:
        return governance_directory.list_people_page(
            db, amo_id=_amo(current_user), page=page, page_size=page_size, filters=filters,
        )
    except ValueError as exc:
        raise _error(str(exc), code="WORKFORCE_GOVERNED_DIRECTORY_INVALID") from exc


@router.get("/people/governed/facets", response_model=governance_schemas.GovernedPeopleFacets)
def governed_people_facets(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _view(db, current_user)
    return governance_directory.list_people_facets(db, amo_id=_amo(current_user))


@router.get("/supervisors", response_model=governance_schemas.SupervisorOptionsPage)
def supervisor_picker(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    org_unit_id: str | None = None,
    exclude_user_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _view(db, current_user)
    try:
        return governance_directory.list_supervisors(
            db, amo_id=_amo(current_user), page=page, page_size=page_size, search=search,
            org_unit_id=org_unit_id, exclude_user_id=exclude_user_id,
        )
    except ValueError as exc:
        raise _error(str(exc), code="WORKFORCE_SUPERVISOR_PICKER_INVALID") from exc


def _audit_catalog(db: Session, *, amo_id: str, actor_user_id: str, entity_type: str, entity_id: str, action: str):
    audit_services.log_event(
        db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type=entity_type,
        entity_id=entity_id, action=action, metadata={"module": "workforce"}, critical=True,
    )


@router.get("/organization-units", response_model=list[governance_schemas.OrgUnitRead])
def organization_units(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _view(db, current_user)
    return governance_directory.list_org_units(db, amo_id=_amo(current_user), include_inactive=include_inactive)


@router.post("/organization-units", response_model=governance_schemas.OrgUnitRead, status_code=status.HTTP_201_CREATED)
def create_organization_unit(
    payload: governance_schemas.OrgUnitWrite,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _manage(db, current_user)
    try:
        row = governance_directory.upsert_org_unit(
            db, amo_id=_amo(current_user), actor_user_id=str(current_user.id), payload=payload,
        )
        _audit_catalog(db, amo_id=_amo(current_user), actor_user_id=str(current_user.id),
                       entity_type="WorkforceOrgUnit", entity_id=row.id, action="create")
        db.commit()
        return row
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_ORG_UNIT_INVALID") from exc


@router.put("/organization-units/{org_unit_id}", response_model=governance_schemas.OrgUnitRead)
def update_organization_unit(
    org_unit_id: str,
    payload: governance_schemas.OrgUnitWrite,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _manage(db, current_user)
    try:
        row = governance_directory.upsert_org_unit(
            db, amo_id=_amo(current_user), actor_user_id=str(current_user.id), payload=payload,
            org_unit_id=org_unit_id,
        )
        _audit_catalog(db, amo_id=_amo(current_user), actor_user_id=str(current_user.id),
                       entity_type="WorkforceOrgUnit", entity_id=row.id, action="update")
        db.commit()
        return row
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_ORG_UNIT_INVALID") from exc


@router.get("/job-families", response_model=list[governance_schemas.JobFamilyRead])
def job_families(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _view(db, current_user)
    return governance_directory.list_job_families(db, amo_id=_amo(current_user), include_inactive=include_inactive)


@router.post("/job-families", response_model=governance_schemas.JobFamilyRead, status_code=status.HTTP_201_CREATED)
def create_job_family(
    payload: governance_schemas.JobFamilyWrite,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _manage(db, current_user)
    try:
        row = governance_directory.upsert_job_family(db, amo_id=_amo(current_user), payload=payload)
        _audit_catalog(db, amo_id=_amo(current_user), actor_user_id=str(current_user.id),
                       entity_type="WorkforceJobFamily", entity_id=str(row.id), action="create")
        db.commit()
        return row
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_JOB_FAMILY_INVALID") from exc


@router.put("/job-families/{row_id}", response_model=governance_schemas.JobFamilyRead)
def update_job_family(
    row_id: str, payload: governance_schemas.JobFamilyWrite,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _manage(db, current_user)
    try:
        row = governance_directory.upsert_job_family(db, amo_id=_amo(current_user), payload=payload, row_id=row_id)
        _audit_catalog(db, amo_id=_amo(current_user), actor_user_id=str(current_user.id),
                       entity_type="WorkforceJobFamily", entity_id=str(row.id), action="update")
        db.commit()
        return row
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_JOB_FAMILY_INVALID") from exc


@router.get("/grades", response_model=list[governance_schemas.GradeRead])
def grades(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _view(db, current_user)
    return governance_directory.list_grades(db, amo_id=_amo(current_user), include_inactive=include_inactive)


@router.post("/grades", response_model=governance_schemas.GradeRead, status_code=status.HTTP_201_CREATED)
def create_grade(
    payload: governance_schemas.GradeWrite,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _manage(db, current_user)
    try:
        row = governance_directory.upsert_grade(db, amo_id=_amo(current_user), payload=payload)
        _audit_catalog(db, amo_id=_amo(current_user), actor_user_id=str(current_user.id),
                       entity_type="WorkforceGrade", entity_id=str(row.id), action="create")
        db.commit()
        return row
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_GRADE_INVALID") from exc


@router.put("/grades/{row_id}", response_model=governance_schemas.GradeRead)
def update_grade(
    row_id: str, payload: governance_schemas.GradeWrite,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _manage(db, current_user)
    try:
        row = governance_directory.upsert_grade(db, amo_id=_amo(current_user), payload=payload, row_id=row_id)
        _audit_catalog(db, amo_id=_amo(current_user), actor_user_id=str(current_user.id),
                       entity_type="WorkforceGrade", entity_id=str(row.id), action="update")
        db.commit()
        return row
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_GRADE_INVALID") from exc


@router.get("/positions", response_model=list[governance_schemas.PositionRead])
def positions(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _view(db, current_user)
    return governance_directory.list_positions(db, amo_id=_amo(current_user), include_inactive=include_inactive)


@router.get("/positions/hierarchy-blueprint", response_model=governance_schemas.HierarchyBlueprintRead)
def position_hierarchy_blueprint(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _view(db, current_user)
    return hierarchy_roles.hierarchy_blueprint(db, amo_id=_amo(current_user))


@router.post("/positions/initialize-kcars-2025", response_model=governance_schemas.HierarchyBlueprintRead)
def initialize_kcars_2025_positions(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _manage(db, current_user)
    try:
        result = hierarchy_roles.initialize_kcar_roles(db, amo_id=_amo(current_user))
        audit_services.log_event(
            db,
            amo_id=_amo(current_user),
            actor_user_id=str(current_user.id),
            entity_type="WorkforceHierarchy",
            entity_id=_amo(current_user),
            action="initialize_kcars_2025_roles",
            after={
                "ready_role_count": result.ready_role_count,
                "created_count": result.created_count,
                "adopted_count": result.adopted_count,
                "updated_count": result.updated_count,
                "supervisor_links_cleared": result.supervisor_links_cleared,
                "accounts_synced": result.accounts_synced,
            },
            metadata={"module": "workforce", "source": "KCAR_2025", "regulations": "19-21"},
            critical=True,
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_HIERARCHY_INVALID") from exc
    except IntegrityError as exc:
        db.rollback()
        raise _error(
            "The hierarchy changed while KCAR roles were being applied. Refresh and retry.",
            code="WORKFORCE_HIERARCHY_CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc


@router.post("/positions", response_model=governance_schemas.PositionRead, status_code=status.HTTP_201_CREATED)
def create_position(
    payload: governance_schemas.PositionWrite,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _manage(db, current_user)
    try:
        row = governance_directory.upsert_position(db, amo_id=_amo(current_user), payload=payload)
        _audit_catalog(db, amo_id=_amo(current_user), actor_user_id=str(current_user.id),
                       entity_type="WorkforcePosition", entity_id=str(row.id), action="create")
        db.commit()
        return row
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_POSITION_INVALID") from exc
    except IntegrityError as exc:
        db.rollback()
        raise _error("Position code or tenant function is already in use.", code="WORKFORCE_POSITION_CONFLICT", status_code=status.HTTP_409_CONFLICT) from exc


@router.put("/positions/{row_id}", response_model=governance_schemas.PositionRead)
def update_position(
    row_id: str, payload: governance_schemas.PositionWrite,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _manage(db, current_user)
    try:
        row = governance_directory.upsert_position(db, amo_id=_amo(current_user), payload=payload, row_id=row_id)
        _audit_catalog(db, amo_id=_amo(current_user), actor_user_id=str(current_user.id),
                       entity_type="WorkforcePosition", entity_id=str(row.id), action="update")
        db.commit()
        return row
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_POSITION_INVALID") from exc
    except IntegrityError as exc:
        db.rollback()
        raise _error("Position code or tenant function is already in use.", code="WORKFORCE_POSITION_CONFLICT", status_code=status.HTTP_409_CONFLICT) from exc
