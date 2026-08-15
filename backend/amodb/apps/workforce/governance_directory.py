"""Governed Workforce directory, hierarchy catalogues and supervisor choices."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Iterable

from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.orm import Session, aliased, joinedload

from ..accounts import models as account_models
from ..foundations import models as foundation_models
from . import (
    governance_models,
    governance_schemas,
    hierarchy_roles,
    hr_people_directory,
    hr_schemas,
    hr_service,
    models,
)

MAX_BATCH_USERS = 10_000


def _today(db: Session, *, amo_id: str) -> date:
    return hr_people_directory._today(db, amo_id=amo_id)


def _effective(placement, *, today: date):
    return and_(
        placement.effective_from <= today,
        or_(placement.effective_to.is_(None), placement.effective_to >= today),
    )


def _human_query(db: Session, *, amo_id: str, include_inactive: bool = False):
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_system_account.is_(False),
    )
    if not include_inactive:
        query = query.filter(account_models.User.is_active.is_(True))
    return query


def _org_rows(db: Session, *, amo_id: str, include_inactive: bool = False):
    query = db.query(governance_models.WorkforceOrgUnit).filter(
        governance_models.WorkforceOrgUnit.amo_id == amo_id
    )
    if not include_inactive:
        query = query.filter(governance_models.WorkforceOrgUnit.is_active.is_(True))
    return query.order_by(
        governance_models.WorkforceOrgUnit.sort_order.asc(),
        governance_models.WorkforceOrgUnit.name.asc(),
        governance_models.WorkforceOrgUnit.id.asc(),
    ).all()


def _hierarchy_maps(rows: Iterable[governance_models.WorkforceOrgUnit]):
    by_id = {str(row.id): row for row in rows}
    children: dict[str | None, list[str]] = defaultdict(list)
    for row in rows:
        children[str(row.parent_id) if row.parent_id else None].append(str(row.id))
    path_ids: dict[str, list[str]] = {}
    path_names: dict[str, list[str]] = {}

    def build(node_id: str, trail: set[str] | None = None):
        if node_id in path_ids:
            return path_ids[node_id], path_names[node_id]
        trail = set(trail or ())
        if node_id in trail:
            raise ValueError("The organisation hierarchy contains a cycle")
        trail.add(node_id)
        node = by_id[node_id]
        parent_id = str(node.parent_id) if node.parent_id else None
        if parent_id and parent_id in by_id:
            parent_path, parent_names = build(parent_id, trail)
        else:
            parent_path, parent_names = [], []
        path_ids[node_id] = [*parent_path, node_id]
        path_names[node_id] = [*parent_names, node.name]
        return path_ids[node_id], path_names[node_id]

    for node_id in by_id:
        build(node_id)
    return by_id, children, path_ids, path_names


def descendant_ids(db: Session, *, amo_id: str, org_unit_id: str, include_self: bool = True) -> list[str]:
    rows = _org_rows(db, amo_id=amo_id, include_inactive=True)
    by_id, children, _, _ = _hierarchy_maps(rows)
    if org_unit_id not in by_id:
        raise ValueError("Organisation unit not found")
    result: list[str] = [org_unit_id] if include_self else []
    stack = list(children.get(org_unit_id, []))
    seen = set(result)
    while stack:
        current = stack.pop()
        if current in seen:
            raise ValueError("The organisation hierarchy contains a cycle")
        seen.add(current)
        result.append(current)
        stack.extend(children.get(current, []))
    return result


def list_org_units(db: Session, *, amo_id: str, include_inactive: bool = False):
    rows = _org_rows(db, amo_id=amo_id, include_inactive=include_inactive)
    _, _, paths, names = _hierarchy_maps(rows)
    return [
        governance_schemas.OrgUnitRead(
            id=str(row.id),
            parent_id=str(row.parent_id) if row.parent_id else None,
            legacy_department_id=str(row.legacy_department_id) if row.legacy_department_id else None,
            code=row.code,
            name=row.name,
            unit_type=row.unit_type,
            description=row.description,
            is_active=bool(row.is_active),
            sort_order=row.sort_order,
            depth=max(0, len(paths[str(row.id)]) - 1),
            path_ids=paths[str(row.id)],
            path_names=names[str(row.id)],
        )
        for row in rows
    ]


def _ensure_org_references(db: Session, *, amo_id: str, payload, row_id: str | None = None):
    if payload.parent_id:
        if row_id and payload.parent_id == row_id:
            raise ValueError("An organisation unit cannot be its own parent")
        parent = db.query(governance_models.WorkforceOrgUnit).filter(
            governance_models.WorkforceOrgUnit.amo_id == amo_id,
            governance_models.WorkforceOrgUnit.id == payload.parent_id,
        ).first()
        if parent is None:
            raise ValueError("Parent organisation unit not found")
        if row_id and payload.parent_id in descendant_ids(db, amo_id=amo_id, org_unit_id=row_id):
            raise ValueError("Moving this unit would create an organisation hierarchy cycle")
    if payload.legacy_department_id:
        department = db.query(account_models.Department).filter(
            account_models.Department.amo_id == amo_id,
            account_models.Department.id == payload.legacy_department_id,
        ).first()
        if department is None:
            raise ValueError("Legacy department projection not found")


def upsert_org_unit(db: Session, *, amo_id: str, actor_user_id: str, payload, org_unit_id: str | None = None):
    _ensure_org_references(db, amo_id=amo_id, payload=payload, row_id=org_unit_id)
    row = None
    if org_unit_id:
        row = db.query(governance_models.WorkforceOrgUnit).filter(
            governance_models.WorkforceOrgUnit.amo_id == amo_id,
            governance_models.WorkforceOrgUnit.id == org_unit_id,
        ).with_for_update().first()
        if row is None:
            raise ValueError("Organisation unit not found")
    else:
        row = governance_models.WorkforceOrgUnit(amo_id=amo_id, created_by_user_id=actor_user_id)
        db.add(row)
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    row.code = row.code.strip().upper()
    row.name = row.name.strip()
    row.updated_by_user_id = actor_user_id
    db.flush()
    return next(item for item in list_org_units(db, amo_id=amo_id, include_inactive=True) if item.id == str(row.id))


def _simple_upsert(db: Session, *, model, schema, amo_id: str, payload, row_id: str | None = None):
    row = None
    if row_id:
        row = db.query(model).filter(model.amo_id == amo_id, model.id == row_id).with_for_update().first()
        if row is None:
            raise ValueError("Governed Workforce record not found")
    else:
        row = model(amo_id=amo_id)
        db.add(row)
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    if hasattr(row, "code"):
        row.code = row.code.strip().upper()
    db.flush()
    if schema is governance_schemas.PositionRead:
        return _position_read(row)
    return schema.model_validate(row)


def list_job_families(db: Session, *, amo_id: str, include_inactive: bool = False):
    query = db.query(governance_models.WorkforceJobFamily).filter(
        governance_models.WorkforceJobFamily.amo_id == amo_id
    )
    if not include_inactive:
        query = query.filter(governance_models.WorkforceJobFamily.is_active.is_(True))
    return [governance_schemas.JobFamilyRead.model_validate(row) for row in query.order_by(
        governance_models.WorkforceJobFamily.name.asc(), governance_models.WorkforceJobFamily.id.asc()
    ).all()]


def upsert_job_family(db: Session, *, amo_id: str, payload, row_id: str | None = None):
    return _simple_upsert(
        db, model=governance_models.WorkforceJobFamily,
        schema=governance_schemas.JobFamilyRead, amo_id=amo_id, payload=payload, row_id=row_id,
    )


def list_grades(db: Session, *, amo_id: str, include_inactive: bool = False):
    query = db.query(governance_models.WorkforceGrade).filter(governance_models.WorkforceGrade.amo_id == amo_id)
    if not include_inactive:
        query = query.filter(governance_models.WorkforceGrade.is_active.is_(True))
    return [governance_schemas.GradeRead.model_validate(row) for row in query.order_by(
        governance_models.WorkforceGrade.rank_order.asc(), governance_models.WorkforceGrade.name.asc(),
        governance_models.WorkforceGrade.id.asc(),
    ).all()]


def upsert_grade(db: Session, *, amo_id: str, payload, row_id: str | None = None):
    return _simple_upsert(
        db, model=governance_models.WorkforceGrade,
        schema=governance_schemas.GradeRead, amo_id=amo_id, payload=payload, row_id=row_id,
    )


def _position_read(row):
    role_source = str(getattr(row, "role_source", "TENANT") or "TENANT")
    management_level = str(getattr(row, "management_level", "STAFF") or "STAFF")
    return governance_schemas.PositionRead(
        id=str(row.id), code=row.code, canonical_title=row.canonical_title,
        job_family_id=str(row.job_family_id) if row.job_family_id else None,
        job_family_name=getattr(getattr(row, "job_family", None), "name", None),
        grade_id=str(row.grade_id) if row.grade_id else None,
        grade_name=getattr(getattr(row, "grade", None), "name", None),
        description=row.description,
        role_source=role_source,
        role_key=getattr(row, "role_key", None),
        management_level=management_level,
        can_have_supervisor=hierarchy_roles.can_have_supervisor(row),
        is_locked=role_source == "KCAR_2025",
        is_supervisory=bool(row.is_supervisory),
        is_active=bool(row.is_active),
    )


def _validate_position_references(db: Session, *, amo_id: str, payload):
    if payload.job_family_id and db.query(governance_models.WorkforceJobFamily.id).filter(
        governance_models.WorkforceJobFamily.amo_id == amo_id,
        governance_models.WorkforceJobFamily.id == payload.job_family_id,
    ).first() is None:
        raise ValueError("Job family not found")
    if payload.grade_id and db.query(governance_models.WorkforceGrade.id).filter(
        governance_models.WorkforceGrade.amo_id == amo_id,
        governance_models.WorkforceGrade.id == payload.grade_id,
    ).first() is None:
        raise ValueError("Grade not found")


def _validate_unique_position_fields(
    db: Session,
    *,
    amo_id: str,
    code: str,
    role_key: str | None,
    row_id: str | None,
):
    duplicate_code = db.query(governance_models.WorkforcePosition.id).filter(
        governance_models.WorkforcePosition.amo_id == amo_id,
        func.upper(governance_models.WorkforcePosition.code) == code.upper(),
        governance_models.WorkforcePosition.id != (row_id or "__new__"),
    ).first()
    if duplicate_code is not None:
        raise ValueError("Position code is already in use")
    if role_key:
        duplicate_role = db.query(governance_models.WorkforcePosition.id).filter(
            governance_models.WorkforcePosition.amo_id == amo_id,
            governance_models.WorkforcePosition.role_key == role_key,
            governance_models.WorkforcePosition.id != (row_id or "__new__"),
        ).first()
        if duplicate_role is not None:
            raise ValueError("This tenant function already has a canonical position")


def list_positions(db: Session, *, amo_id: str, include_inactive: bool = False):
    query = db.query(governance_models.WorkforcePosition).options(
        joinedload(governance_models.WorkforcePosition.job_family),
        joinedload(governance_models.WorkforcePosition.grade),
    ).filter(governance_models.WorkforcePosition.amo_id == amo_id)
    if not include_inactive:
        query = query.filter(governance_models.WorkforcePosition.is_active.is_(True))
    return [_position_read(row) for row in query.order_by(
        governance_models.WorkforcePosition.canonical_title.asc(), governance_models.WorkforcePosition.id.asc()
    ).all()]


def upsert_position(db: Session, *, amo_id: str, payload, row_id: str | None = None):
    _validate_position_references(db, amo_id=amo_id, payload=payload)
    row = None
    if row_id:
        row = db.query(governance_models.WorkforcePosition).filter(
            governance_models.WorkforcePosition.amo_id == amo_id,
            governance_models.WorkforcePosition.id == row_id,
        ).with_for_update().first()
        if row is None:
            raise ValueError("Governed Workforce record not found")
    regulatory = row is not None and str(row.role_source or "TENANT") == "KCAR_2025"
    code = payload.code.strip().upper()
    title = payload.canonical_title.strip()
    role_key = row.role_key if regulatory else payload.tenant_function
    if regulatory:
        if code != row.code or title != row.canonical_title:
            raise ValueError("KCAR position identity is protected; only its family, grade and description may be edited")
        if payload.management_level != row.management_level or payload.tenant_function:
            raise ValueError("KCAR management classification is protected")
        if not payload.is_active or not payload.is_supervisory:
            raise ValueError("Required KCAR management positions must remain active and supervisory")
    _validate_unique_position_fields(
        db,
        amo_id=amo_id,
        code=code,
        role_key=role_key,
        row_id=row_id,
    )
    if row is None:
        row = governance_models.WorkforcePosition(amo_id=amo_id, role_source="TENANT")
        db.add(row)
    row.code = code
    row.canonical_title = title
    row.job_family_id = payload.job_family_id
    row.grade_id = payload.grade_id
    row.description = payload.description
    if not regulatory:
        row.role_source = "TENANT"
        row.role_key = role_key
        row.management_level = payload.management_level
        row.is_supervisory = bool(
            payload.is_supervisory or payload.management_level in {"SUPERVISOR", "MANAGER", "EXECUTIVE"}
        )
        row.is_active = payload.is_active
    db.flush()
    if not hierarchy_roles.can_have_supervisor(row):
        hierarchy_roles.clear_current_management_supervisors(
            db,
            amo_id=amo_id,
            position_id=str(row.id),
            on_date=_today(db, amo_id=amo_id),
        )
        db.flush()
    return _position_read(row)


def _placement_exists(*, amo_id: str, today: date, conditions: list):
    placement = governance_models.WorkforcePersonPlacement
    return exists().where(
        placement.amo_id == amo_id,
        placement.user_id == account_models.User.id,
        _effective(placement, today=today),
        *conditions,
    )


def _apply_governed_filters(query, *, db: Session, amo_id: str, filters, today: date):
    placement = governance_models.WorkforcePersonPlacement
    if filters.org_unit_id:
        ids = (
            descendant_ids(db, amo_id=amo_id, org_unit_id=filters.org_unit_id)
            if filters.include_descendants else [filters.org_unit_id]
        )
        conditions = [placement.org_unit_id.in_(ids)]
        if filters.placement_type:
            conditions.append(placement.placement_type == filters.placement_type)
        query = query.filter(_placement_exists(amo_id=amo_id, today=today, conditions=conditions))
    elif filters.placement_type:
        query = query.filter(_placement_exists(
            amo_id=amo_id, today=today, conditions=[placement.placement_type == filters.placement_type]
        ))
    if filters.position_id:
        query = query.filter(_placement_exists(
            amo_id=amo_id, today=today, conditions=[placement.position_id == filters.position_id]
        ))
    if filters.job_family_id:
        query = query.filter(exists().where(
            placement.amo_id == amo_id, placement.user_id == account_models.User.id,
            _effective(placement, today=today),
            governance_models.WorkforcePosition.id == placement.position_id,
            governance_models.WorkforcePosition.amo_id == amo_id,
            governance_models.WorkforcePosition.job_family_id == filters.job_family_id,
        ))
    if filters.grade_id:
        query = query.filter(exists().where(
            placement.amo_id == amo_id, placement.user_id == account_models.User.id,
            _effective(placement, today=today),
            governance_models.WorkforcePosition.id == placement.position_id,
            governance_models.WorkforcePosition.amo_id == amo_id,
            governance_models.WorkforcePosition.grade_id == filters.grade_id,
        ))
    if filters.supervisor_user_id:
        query = query.filter(or_(
            _placement_exists(
                amo_id=amo_id, today=today,
                conditions=[placement.supervisor_user_id == filters.supervisor_user_id],
            ),
            hr_people_directory._chosen_contract_match(
                amo_id=amo_id, today=today,
                conditions=[models.EmploymentContract.supervisor_user_id == filters.supervisor_user_id],
            ),
        ))
    if filters.secondary_base_station_id:
        query = query.filter(hr_people_directory._chosen_contract_match(
            amo_id=amo_id, today=today,
            conditions=[models.EmploymentContract.secondary_base_station_id == filters.secondary_base_station_id],
        ))
    contract_conditions = []
    if filters.contract_effective_from_on_or_after:
        contract_conditions.append(models.EmploymentContract.effective_from >= filters.contract_effective_from_on_or_after)
    if filters.contract_effective_from_on_or_before:
        contract_conditions.append(models.EmploymentContract.effective_from <= filters.contract_effective_from_on_or_before)
    if filters.contract_effective_to_on_or_after:
        contract_conditions.append(models.EmploymentContract.effective_to >= filters.contract_effective_to_on_or_after)
    if filters.contract_effective_to_on_or_before:
        contract_conditions.append(models.EmploymentContract.effective_to <= filters.contract_effective_to_on_or_before)
    if contract_conditions:
        query = query.filter(hr_people_directory._chosen_contract_match(
            amo_id=amo_id, today=today, conditions=contract_conditions
        ))
    if filters.lifecycle_state == "INACTIVE":
        query = query.filter(account_models.User.is_active.is_(False))
    elif filters.lifecycle_state:
        query = query.filter(account_models.User.is_active.is_(True))
        if filters.lifecycle_state == "OFFBOARDING_SCHEDULED":
            query = query.filter(exists().where(
                governance_models.WorkforceOffboardingPlan.amo_id == amo_id,
                governance_models.WorkforceOffboardingPlan.user_id == account_models.User.id,
                governance_models.WorkforceOffboardingPlan.status == "SCHEDULED",
            ))
        else:
            query = query.filter(hr_people_directory._chosen_contract_match(
                amo_id=amo_id, today=today,
                conditions=[models.EmploymentContract.employment_status == filters.lifecycle_state],
            ))
    return query


def _governed_sort(query, *, amo_id: str, filters, today: date):
    if filters.sort_by in {"name", "staff_code", "department", "role", "position_title"}:
        return hr_people_directory._apply_sort(query, filters=filters)
    direction = filters.sort_dir
    placement = aliased(governance_models.WorkforcePersonPlacement)
    position = aliased(governance_models.WorkforcePosition)
    family = aliased(governance_models.WorkforceJobFamily)
    grade = aliased(governance_models.WorkforceGrade)
    supervisor = aliased(account_models.User)
    base = aliased(foundation_models.BaseStation)
    contract = aliased(models.EmploymentContract)

    placement_base = (
        placement.amo_id == amo_id,
        placement.user_id == account_models.User.id,
        placement.placement_type == "PRIMARY",
        placement.effective_from <= today,
        or_(placement.effective_to.is_(None), placement.effective_to >= today),
    )
    expressions = {
        "org_unit": db_scalar(governance_models.WorkforceOrgUnit.name, placement, *placement_base,
                              governance_models.WorkforceOrgUnit.id == placement.org_unit_id),
        "position": db_scalar(position.canonical_title, placement, *placement_base,
                              position.id == placement.position_id),
        "job_family": db_scalar(family.name, placement, *placement_base,
                                position.id == placement.position_id, family.id == position.job_family_id),
        "grade": db_scalar(grade.rank_order, placement, *placement_base,
                           position.id == placement.position_id, grade.id == position.grade_id),
        "supervisor": db_scalar(supervisor.full_name, placement, *placement_base,
                                supervisor.id == placement.supervisor_user_id),
        "contract_start": db_scalar(contract.effective_from, contract,
                                    contract.amo_id == amo_id, contract.user_id == account_models.User.id),
        "contract_end": db_scalar(contract.effective_to, contract,
                                  contract.amo_id == amo_id, contract.user_id == account_models.User.id),
        "primary_base": db_scalar(base.name, contract,
                                  contract.amo_id == amo_id, contract.user_id == account_models.User.id,
                                  base.id == contract.primary_base_station_id),
        "secondary_base": db_scalar(base.name, contract,
                                    contract.amo_id == amo_id, contract.user_id == account_models.User.id,
                                    base.id == contract.secondary_base_station_id),
        "employment_status": db_scalar(contract.employment_status, contract,
                                       contract.amo_id == amo_id, contract.user_id == account_models.User.id),
    }
    expression = expressions[filters.sort_by]
    ordered = expression.desc().nullslast() if direction == "desc" else expression.asc().nullslast()
    return query.order_by(ordered, account_models.User.full_name.asc(), account_models.User.id.asc())


def db_scalar(column, source, *conditions):
    return (
        source_query(column, source, *conditions)
        .limit(1)
        .scalar_subquery()
    )


def source_query(column, source, *conditions):
    from sqlalchemy import select
    return select(column).where(*conditions).order_by(column.asc())


def _placement_read(row, *, path_names: dict[str, list[str]]):
    position = getattr(row, "position", None)
    family = getattr(position, "job_family", None) if position else None
    grade = getattr(position, "grade", None) if position else None
    return governance_schemas.PlacementRead(
        id=str(row.id), user_id=str(row.user_id), org_unit_id=str(row.org_unit_id),
        org_unit_name=row.org_unit.name, org_path_names=path_names.get(str(row.org_unit_id), [row.org_unit.name]),
        position_id=str(row.position_id) if row.position_id else None,
        position_title=getattr(position, "canonical_title", None), preferred_title=row.preferred_title,
        job_family_id=str(position.job_family_id) if position and position.job_family_id else None,
        job_family_name=getattr(family, "name", None),
        grade_id=str(position.grade_id) if position and position.grade_id else None,
        grade_name=getattr(grade, "name", None), placement_type=row.placement_type,
        base_station_id=str(row.base_station_id) if row.base_station_id else None,
        base_station_name=getattr(getattr(row, "base_station", None), "name", None),
        supervisor_user_id=str(row.supervisor_user_id) if row.supervisor_user_id else None,
        supervisor_name=getattr(getattr(row, "supervisor", None), "full_name", None),
        effective_from=row.effective_from, effective_to=row.effective_to,
    )


def _enrich_people(db: Session, *, amo_id: str, users, base_items, today: date):
    user_ids = [str(user.id) for user in users]
    org_rows = _org_rows(db, amo_id=amo_id, include_inactive=True)
    _, _, _, path_names = _hierarchy_maps(org_rows)
    placements = db.query(governance_models.WorkforcePersonPlacement).options(
        joinedload(governance_models.WorkforcePersonPlacement.org_unit),
        joinedload(governance_models.WorkforcePersonPlacement.position).joinedload(governance_models.WorkforcePosition.job_family),
        joinedload(governance_models.WorkforcePersonPlacement.position).joinedload(governance_models.WorkforcePosition.grade),
        joinedload(governance_models.WorkforcePersonPlacement.base_station),
        joinedload(governance_models.WorkforcePersonPlacement.supervisor),
    ).filter(
        governance_models.WorkforcePersonPlacement.amo_id == amo_id,
        governance_models.WorkforcePersonPlacement.user_id.in_(user_ids or ["__none__"]),
        _effective(governance_models.WorkforcePersonPlacement, today=today),
    ).order_by(
        governance_models.WorkforcePersonPlacement.user_id.asc(),
        case((governance_models.WorkforcePersonPlacement.placement_type == "PRIMARY", 0),
             (governance_models.WorkforcePersonPlacement.placement_type == "SECONDARY", 1), else_=2),
        governance_models.WorkforcePersonPlacement.effective_from.desc(),
        governance_models.WorkforcePersonPlacement.id.asc(),
    ).all()
    placement_by_user: dict[str, list] = defaultdict(list)
    for row in placements:
        placement_by_user[str(row.user_id)].append(row)
    plans = {str(row.user_id): row for row in db.query(governance_models.WorkforceOffboardingPlan).filter(
        governance_models.WorkforceOffboardingPlan.amo_id == amo_id,
        governance_models.WorkforceOffboardingPlan.user_id.in_(user_ids or ["__none__"]),
        governance_models.WorkforceOffboardingPlan.status == "SCHEDULED",
    ).order_by(governance_models.WorkforceOffboardingPlan.effective_on.asc()).all()}
    contracts = hr_service._readiness_contracts_by_user(db, amo_id=amo_id, user_ids=user_ids, on_date=today)
    bases = {str(row.id): row for row in db.query(foundation_models.BaseStation).filter(
        foundation_models.BaseStation.amo_id == amo_id
    ).all()}
    user_by_id = {str(user.id): user for user in users}
    result = []
    for base_item in base_items:
        user_id = base_item.user_id
        rows = placement_by_user.get(user_id, [])
        primary = next((row for row in rows if row.placement_type == "PRIMARY"), None)
        secondary = [_placement_read(row, path_names=path_names) for row in rows if row.placement_type == "SECONDARY"]
        matrix = [_placement_read(row, path_names=path_names) for row in rows if row.placement_type == "MATRIX"]
        position = getattr(primary, "position", None) if primary else None
        family = getattr(position, "job_family", None) if position else None
        grade = getattr(position, "grade", None) if position else None
        contract = contracts.get(user_id)
        secondary_base = bases.get(str(contract.secondary_base_station_id)) if contract and contract.secondary_base_station_id else None
        user = user_by_id[user_id]
        plan = plans.get(user_id)
        lifecycle = "INACTIVE" if not user.is_active else ("OFFBOARDING_SCHEDULED" if plan else (base_item.employment_status or "ACTIVE"))
        result.append(governance_schemas.GovernedPersonReadiness(**base_item.model_dump(),
            primary_org_unit_id=str(primary.org_unit_id) if primary else None,
            primary_org_unit_name=getattr(getattr(primary, "org_unit", None), "name", None),
            primary_org_path=path_names.get(str(primary.org_unit_id), []) if primary else [],
            canonical_position_id=str(primary.position_id) if primary and primary.position_id else None,
            canonical_position_title=getattr(position, "canonical_title", None),
            preferred_title=getattr(primary, "preferred_title", None),
            job_family_id=str(position.job_family_id) if position and position.job_family_id else None,
            job_family_name=getattr(family, "name", None),
            grade_id=str(position.grade_id) if position and position.grade_id else None,
            grade_name=getattr(grade, "name", None),
            supervisor_user_id=(str(primary.supervisor_user_id) if primary and primary.supervisor_user_id else
                                (str(contract.supervisor_user_id) if contract and contract.supervisor_user_id else None)),
            can_have_supervisor=position is None or hierarchy_roles.can_have_supervisor(position),
            secondary_org_units=secondary, matrix_org_units=matrix,
            secondary_base_station_id=str(contract.secondary_base_station_id) if contract and contract.secondary_base_station_id else None,
            secondary_base_code=getattr(secondary_base, "code", None), lifecycle_state=lifecycle,
            offboarding_effective_on=getattr(plan, "effective_on", None),
        ))
    return result


def list_people_page(db: Session, *, amo_id: str, page: int, page_size: int, filters):
    today = _today(db, amo_id=amo_id)
    now = hr_service._utcnow()
    include_inactive = filters.lifecycle_state == "INACTIVE"
    query = _human_query(db, amo_id=amo_id, include_inactive=include_inactive)
    query = hr_people_directory._apply_filters(
        query, amo_id=amo_id, filters=filters, today=today, now=now
    )
    query = _apply_governed_filters(query, db=db, amo_id=amo_id, filters=filters, today=today)
    safe_page_size = max(1, min(int(page_size), 250))
    safe_page = max(1, int(page))
    total = int(query.order_by(None).count())
    pages = math.ceil(total / safe_page_size) if total else 0
    if pages and safe_page > pages:
        safe_page = pages
    users = _governed_sort(query, amo_id=amo_id, filters=filters, today=today).options(
        joinedload(account_models.User.department)
    ).offset((safe_page - 1) * safe_page_size).limit(safe_page_size).all()
    base_items = hr_people_directory._serialize_users(
        db, amo_id=amo_id, users=users, today=today, now=now
    )
    return governance_schemas.GovernedPeoplePage(
        items=_enrich_people(db, amo_id=amo_id, users=users, base_items=base_items, today=today),
        page=safe_page, page_size=safe_page_size, total=total, pages=pages,
    )


def resolve_selection_user_ids(db: Session, *, amo_id: str, selection) -> list[str]:
    today = _today(db, amo_id=amo_id)
    now = hr_service._utcnow()
    filters = selection.filters
    include_inactive = getattr(filters, "lifecycle_state", None) == "INACTIVE"
    query = _human_query(db, amo_id=amo_id, include_inactive=include_inactive)
    if selection.mode == "EXPLICIT":
        query = query.filter(account_models.User.id.in_(selection.user_ids))
    else:
        query = hr_people_directory._apply_filters(
            query, amo_id=amo_id, filters=filters, today=today, now=now
        )
        query = _apply_governed_filters(query, db=db, amo_id=amo_id, filters=filters, today=today)
        if selection.exclude_user_ids:
            query = query.filter(account_models.User.id.notin_(selection.exclude_user_ids))
    total = int(query.order_by(None).count())
    if total > MAX_BATCH_USERS:
        raise ValueError(f"This batch matches {total} users; narrow the filters to {MAX_BATCH_USERS} or fewer.")
    return [str(user_id) for (user_id,) in query.with_entities(account_models.User.id).order_by(
        account_models.User.full_name.asc(), account_models.User.id.asc()
    ).all()]


def list_supervisors(db: Session, *, amo_id: str, page: int, page_size: int, search: str | None = None,
                     org_unit_id: str | None = None, exclude_user_id: str | None = None):
    today = _today(db, amo_id=amo_id)
    query = _human_query(db, amo_id=amo_id).filter(
        hr_people_directory._effective_contract_exists(amo_id=amo_id, today=today)
    )
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(account_models.User.full_name.ilike(term),
                                 account_models.User.staff_code.ilike(term),
                                 account_models.User.position_title.ilike(term)))
    if exclude_user_id:
        query = query.filter(account_models.User.id != exclude_user_id)
    if org_unit_id:
        ids = descendant_ids(db, amo_id=amo_id, org_unit_id=org_unit_id)
        query = query.filter(_placement_exists(
            amo_id=amo_id, today=today,
            conditions=[governance_models.WorkforcePersonPlacement.org_unit_id.in_(ids)],
        ))
    total = int(query.order_by(None).count())
    safe_size = max(1, min(int(page_size), 100))
    pages = math.ceil(total / safe_size) if total else 0
    safe_page = min(max(1, int(page)), pages or 1)
    users = query.order_by(account_models.User.full_name.asc(), account_models.User.id.asc()).offset(
        (safe_page - 1) * safe_size
    ).limit(safe_size).all()
    user_ids = [str(user.id) for user in users]
    primary = {str(row.user_id): row for row in db.query(governance_models.WorkforcePersonPlacement).options(
        joinedload(governance_models.WorkforcePersonPlacement.org_unit),
        joinedload(governance_models.WorkforcePersonPlacement.position),
    ).filter(
        governance_models.WorkforcePersonPlacement.amo_id == amo_id,
        governance_models.WorkforcePersonPlacement.user_id.in_(user_ids or ["__none__"]),
        governance_models.WorkforcePersonPlacement.placement_type == "PRIMARY",
        _effective(governance_models.WorkforcePersonPlacement, today=today),
    ).order_by(governance_models.WorkforcePersonPlacement.effective_from.desc()).all()}
    return governance_schemas.SupervisorOptionsPage(
        items=[governance_schemas.SupervisorOption(
            user_id=str(user.id), staff_code=user.staff_code, full_name=user.full_name,
            position_title=(getattr(getattr(primary.get(str(user.id)), "position", None), "canonical_title", None)
                            or user.position_title),
            org_unit_name=getattr(getattr(primary.get(str(user.id)), "org_unit", None), "name", None),
            is_supervisory_position=bool(getattr(getattr(primary.get(str(user.id)), "position", None), "is_supervisory", False)),
        ) for user in users],
        page=safe_page, page_size=safe_size, total=total, pages=pages,
    )


def list_people_facets(db: Session, *, amo_id: str):
    legacy = hr_people_directory.list_people_facets(db, amo_id=amo_id)
    today = _today(db, amo_id=amo_id)
    human = and_(account_models.User.amo_id == amo_id, account_models.User.is_system_account.is_(False))
    active_placement = and_(
        governance_models.WorkforcePersonPlacement.amo_id == amo_id,
        _effective(governance_models.WorkforcePersonPlacement, today=today),
    )
    org_rows = db.query(governance_models.WorkforceOrgUnit.id, governance_models.WorkforceOrgUnit.name,
                        func.count(func.distinct(governance_models.WorkforcePersonPlacement.user_id))).join(
        governance_models.WorkforcePersonPlacement,
        governance_models.WorkforcePersonPlacement.org_unit_id == governance_models.WorkforceOrgUnit.id,
    ).join(account_models.User, account_models.User.id == governance_models.WorkforcePersonPlacement.user_id).filter(
        governance_models.WorkforceOrgUnit.amo_id == amo_id, governance_models.WorkforceOrgUnit.is_active.is_(True),
        active_placement, human,
    ).group_by(governance_models.WorkforceOrgUnit.id, governance_models.WorkforceOrgUnit.name).order_by(
        governance_models.WorkforceOrgUnit.name.asc()).all()
    position_rows = db.query(governance_models.WorkforcePosition.id, governance_models.WorkforcePosition.canonical_title,
                             func.count(func.distinct(governance_models.WorkforcePersonPlacement.user_id))).join(
        governance_models.WorkforcePersonPlacement,
        governance_models.WorkforcePersonPlacement.position_id == governance_models.WorkforcePosition.id,
    ).join(account_models.User, account_models.User.id == governance_models.WorkforcePersonPlacement.user_id).filter(
        governance_models.WorkforcePosition.amo_id == amo_id, governance_models.WorkforcePosition.is_active.is_(True),
        active_placement, human,
    ).group_by(governance_models.WorkforcePosition.id, governance_models.WorkforcePosition.canonical_title).order_by(
        governance_models.WorkforcePosition.canonical_title.asc()).all()
    def options(rows):
        return [hr_schemas.HrFilterOption(value=str(value), label=str(label), count=int(count or 0))
                for value, label, count in rows]
    family_rows = db.query(governance_models.WorkforceJobFamily.id, governance_models.WorkforceJobFamily.name,
                           func.count(func.distinct(governance_models.WorkforcePersonPlacement.user_id))).join(
        governance_models.WorkforcePosition,
        governance_models.WorkforcePosition.job_family_id == governance_models.WorkforceJobFamily.id,
    ).join(governance_models.WorkforcePersonPlacement,
           governance_models.WorkforcePersonPlacement.position_id == governance_models.WorkforcePosition.id).join(
        account_models.User, account_models.User.id == governance_models.WorkforcePersonPlacement.user_id).filter(
        governance_models.WorkforceJobFamily.amo_id == amo_id, active_placement, human,
    ).group_by(governance_models.WorkforceJobFamily.id, governance_models.WorkforceJobFamily.name).order_by(
        governance_models.WorkforceJobFamily.name.asc()).all()
    grade_rows = db.query(governance_models.WorkforceGrade.id, governance_models.WorkforceGrade.name,
                          func.count(func.distinct(governance_models.WorkforcePersonPlacement.user_id))).join(
        governance_models.WorkforcePosition, governance_models.WorkforcePosition.grade_id == governance_models.WorkforceGrade.id,
    ).join(governance_models.WorkforcePersonPlacement,
           governance_models.WorkforcePersonPlacement.position_id == governance_models.WorkforcePosition.id).join(
        account_models.User, account_models.User.id == governance_models.WorkforcePersonPlacement.user_id).filter(
        governance_models.WorkforceGrade.amo_id == amo_id, active_placement, human,
    ).group_by(governance_models.WorkforceGrade.id, governance_models.WorkforceGrade.name,
               governance_models.WorkforceGrade.rank_order).order_by(governance_models.WorkforceGrade.rank_order.asc()).all()
    supervisor_rows = db.query(account_models.User.id, account_models.User.full_name,
                               func.count(func.distinct(governance_models.WorkforcePersonPlacement.user_id))).join(
        governance_models.WorkforcePersonPlacement,
        governance_models.WorkforcePersonPlacement.supervisor_user_id == account_models.User.id,
    ).filter(account_models.User.amo_id == amo_id, active_placement).group_by(
        account_models.User.id, account_models.User.full_name).order_by(account_models.User.full_name.asc()).all()
    secondary_base_rows = db.query(foundation_models.BaseStation.id, foundation_models.BaseStation.name,
                                   func.count(func.distinct(models.EmploymentContract.user_id))).join(
        models.EmploymentContract,
        models.EmploymentContract.secondary_base_station_id == foundation_models.BaseStation.id,
    ).filter(foundation_models.BaseStation.amo_id == amo_id).group_by(
        foundation_models.BaseStation.id, foundation_models.BaseStation.name).order_by(foundation_models.BaseStation.name.asc()).all()
    placement_rows = db.query(governance_models.WorkforcePersonPlacement.placement_type,
                              func.count(func.distinct(governance_models.WorkforcePersonPlacement.user_id))).filter(
        active_placement).group_by(governance_models.WorkforcePersonPlacement.placement_type).all()
    lifecycle = []
    for value, label in (("ACTIVE", "Active"), ("ONBOARDING", "Onboarding"), ("SUSPENDED", "Suspended"),
                         ("OFFBOARDING_SCHEDULED", "Offboarding scheduled"), ("INACTIVE", "Inactive")):
        lifecycle.append(hr_schemas.HrFilterOption(
            value=value, label=label,
            count=int(_apply_governed_filters(
                hr_people_directory._apply_filters(
                    _human_query(db, amo_id=amo_id, include_inactive=value == "INACTIVE"),
                    amo_id=amo_id, filters=governance_schemas.GovernedPeopleFilterInput(lifecycle_state=value),
                    today=today, now=hr_service._utcnow(),
                ), db=db, amo_id=amo_id,
                filters=governance_schemas.GovernedPeopleFilterInput(lifecycle_state=value), today=today,
            ).order_by(None).count()),
        ))
    return governance_schemas.GovernedPeopleFacets(
        **legacy.model_dump(), org_units=options(org_rows), positions=options(position_rows),
        job_families=options(family_rows), grades=options(grade_rows), supervisors=options(supervisor_rows),
        secondary_bases=options(secondary_base_rows),
        placement_types=[hr_schemas.HrFilterOption(value=str(value), label=str(value).title(), count=int(count or 0))
                         for value, count in placement_rows], lifecycle_states=lifecycle,
    )
