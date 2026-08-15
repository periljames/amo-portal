"""Scalable Workforce people directory and controlled batch operations.

The original HR register assembled every active tenant user and every related
contract, pattern and leave row before applying search and pagination in Python.
That behavior was acceptable for small demonstrations but is not appropriate for
large tenants. This module keeps filtering, sorting, counting and pagination in
SQL and only hydrates Workforce readiness for the requested page.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import Session, joinedload

from ..accounts import models as account_models
from ..foundations import models as foundation_models
from . import hr_schemas, hr_service, models, schemas, services

MAX_BATCH_USERS = 10_000
_BATCH_CHUNK_SIZE = 500


def _today(db: Session, *, amo_id: str) -> date:
    return datetime.now(hr_service._amo_zone(db, amo_id=amo_id)).date()


def _effective_contract_predicate(*, amo_id: str, today: date):
    return and_(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == account_models.User.id,
        models.EmploymentContract.employment_status.in_([
            models.EmploymentStatus.ACTIVE,
            models.EmploymentStatus.ONBOARDING,
            models.EmploymentStatus.SUSPENDED,
        ]),
        models.EmploymentContract.effective_from <= today,
        or_(
            models.EmploymentContract.effective_to.is_(None),
            models.EmploymentContract.effective_to >= today,
        ),
    )


def _future_contract_predicate(*, amo_id: str, today: date):
    return and_(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == account_models.User.id,
        models.EmploymentContract.employment_status.in_([
            models.EmploymentStatus.ACTIVE,
            models.EmploymentStatus.ONBOARDING,
            models.EmploymentStatus.SUSPENDED,
        ]),
        models.EmploymentContract.effective_from > today,
    )


def _effective_contract_exists(*, amo_id: str, today: date):
    return exists().where(_effective_contract_predicate(amo_id=amo_id, today=today))


def _future_contract_exists(*, amo_id: str, today: date):
    return exists().where(_future_contract_predicate(amo_id=amo_id, today=today))


def _chosen_contract_match(*, amo_id: str, today: date, conditions: Iterable):
    effective_exists = _effective_contract_exists(amo_id=amo_id, today=today)
    effective_match = exists().where(
        _effective_contract_predicate(amo_id=amo_id, today=today),
        *conditions,
    )
    future_match = exists().where(
        _future_contract_predicate(amo_id=amo_id, today=today),
        *conditions,
    )
    return or_(effective_match, and_(~effective_exists, future_match))


def _active_pattern_exists(*, amo_id: str, today: date, pattern_id: Optional[str] = None):
    clauses = [
        models.EmployeeWorkPatternAssignment.amo_id == amo_id,
        models.EmployeeWorkPatternAssignment.user_id == account_models.User.id,
        models.EmployeeWorkPatternAssignment.effective_from <= today,
        or_(
            models.EmployeeWorkPatternAssignment.effective_to.is_(None),
            models.EmployeeWorkPatternAssignment.effective_to >= today,
        ),
        models.WorkPattern.id == models.EmployeeWorkPatternAssignment.work_pattern_id,
        models.WorkPattern.amo_id == amo_id,
        models.WorkPattern.is_active.is_(True),
    ]
    if pattern_id:
        clauses.append(models.EmployeeWorkPatternAssignment.work_pattern_id == pattern_id)
    return exists().where(*clauses)


def _approved_leave_exists(*, amo_id: str, now: datetime):
    return exists().where(
        models.LeaveRequest.amo_id == amo_id,
        models.LeaveRequest.user_id == account_models.User.id,
        models.LeaveRequest.status == models.LeaveRequestStatus.HR_APPROVED,
        models.LeaveRequest.starts_at <= now,
        models.LeaveRequest.ends_at > now,
    )


def _ready_condition(*, amo_id: str, today: date, now: datetime):
    active_contract = exists().where(
        _effective_contract_predicate(amo_id=amo_id, today=today),
        models.EmploymentContract.employment_status == models.EmploymentStatus.ACTIVE,
        models.EmploymentContract.primary_base_station_id.is_not(None),
    )
    return and_(
        active_contract,
        _active_pattern_exists(amo_id=amo_id, today=today),
        ~_approved_leave_exists(amo_id=amo_id, now=now),
    )


def _blocked_condition(*, amo_id: str, today: date):
    return exists().where(
        _effective_contract_predicate(amo_id=amo_id, today=today),
        models.EmploymentContract.employment_status == models.EmploymentStatus.SUSPENDED,
    )


def _base_user_query(db: Session, *, amo_id: str):
    return db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )


def _automatic_pattern_resolution(
    db: Session,
    *,
    amo_id: str,
    today: date,
) -> tuple[set[str], set[str]]:
    user_ids = [
        str(user_id)
        for (user_id,) in _base_user_query(db, amo_id=amo_id)
        .with_entities(account_models.User.id)
        .all()
    ]
    if not user_ids:
        return set(), set()
    preview = services.preview_patterns(
        db,
        amo_id=amo_id,
        payload=schemas.PatternPreviewRequest(
            from_date=today,
            to_date=today,
            user_ids=user_ids,
        ),
    )
    resolved = {
        str(row.user_id)
        for row in preview.items
        if row.resolution_source == "RULE" and row.pattern_id
    }
    ambiguous = {
        str(row.user_id)
        for row in preview.items
        if row.resolution_source == "RULE" and "AMBIGUOUS_PATTERN_RULE" in row.conflicts
    }
    return resolved, ambiguous


def _apply_filters(
    query,
    *,
    amo_id: str,
    filters: hr_schemas.HrPeopleFilterInput,
    today: date,
    now: datetime,
    automatic_patterned_user_ids: set[str] | None = None,
    ambiguous_pattern_user_ids: set[str] | None = None,
):
    effective_exists = _effective_contract_exists(amo_id=amo_id, today=today)
    future_exists = _future_contract_exists(amo_id=amo_id, today=today)
    managed_pattern_id = hr_service._default_day_system_id(
        amo_id=amo_id,
        system_key=hr_service._DEFAULT_DAY_PATTERN_KEY,
    )
    active_pattern = _active_pattern_exists(amo_id=amo_id, today=today)
    default_pattern = _active_pattern_exists(
        amo_id=amo_id,
        today=today,
        pattern_id=managed_pattern_id,
    )
    ready = _ready_condition(amo_id=amo_id, today=today, now=now)
    blocked = _blocked_condition(amo_id=amo_id, today=today)
    automatic_ids = automatic_patterned_user_ids or set()
    ambiguous_ids = ambiguous_pattern_user_ids or set()
    automatic_pattern = account_models.User.id.in_(automatic_ids) if automatic_ids else None
    if automatic_pattern is not None:
        automatic_ready = and_(
            automatic_pattern,
            exists().where(
                _effective_contract_predicate(amo_id=amo_id, today=today),
                models.EmploymentContract.employment_status == models.EmploymentStatus.ACTIVE,
                models.EmploymentContract.primary_base_station_id.is_not(None),
            ),
            ~_approved_leave_exists(amo_id=amo_id, now=now),
        )
        if ambiguous_ids:
            automatic_ready = and_(automatic_ready, account_models.User.id.notin_(ambiguous_ids))
        ready = or_(ready, automatic_ready)

    if filters.search:
        term = f"%{filters.search.strip()}%"
        group_search = exists().where(
            account_models.UserGroupMember.user_id == account_models.User.id,
            account_models.UserGroup.id == account_models.UserGroupMember.group_id,
            account_models.UserGroup.amo_id == amo_id,
            account_models.UserGroup.is_active.is_(True),
            or_(
                account_models.UserGroup.code.ilike(term),
                account_models.UserGroup.name.ilike(term),
            ),
        )
        department_search = exists().where(
            account_models.Department.id == account_models.User.department_id,
            account_models.Department.amo_id == amo_id,
            or_(
                account_models.Department.code.ilike(term),
                account_models.Department.name.ilike(term),
            ),
        )
        contract_search = exists().where(
            models.EmploymentContract.amo_id == amo_id,
            models.EmploymentContract.user_id == account_models.User.id,
            or_(
                models.EmploymentContract.payroll_number.ilike(term),
                models.EmploymentContract.cost_centre.ilike(term),
            ),
        )
        base_search = exists().where(
            models.EmploymentContract.amo_id == amo_id,
            models.EmploymentContract.user_id == account_models.User.id,
            foundation_models.BaseStation.id == models.EmploymentContract.primary_base_station_id,
            foundation_models.BaseStation.amo_id == amo_id,
            or_(
                foundation_models.BaseStation.code.ilike(term),
                foundation_models.BaseStation.name.ilike(term),
            ),
        )
        query = query.filter(or_(
            account_models.User.full_name.ilike(term),
            account_models.User.first_name.ilike(term),
            account_models.User.last_name.ilike(term),
            account_models.User.email.ilike(term),
            account_models.User.staff_code.ilike(term),
            account_models.User.position_title.ilike(term),
            department_search,
            contract_search,
            base_search,
            group_search,
        ))

    if filters.department_id:
        query = query.filter(account_models.User.department_id == filters.department_id)
    if filters.role:
        query = query.filter(account_models.User.role == filters.role)
    if filters.position_title:
        query = query.filter(account_models.User.position_title == filters.position_title)
    if filters.group_id:
        query = query.filter(exists().where(
            account_models.UserGroupMember.user_id == account_models.User.id,
            account_models.UserGroupMember.group_id == filters.group_id,
            account_models.UserGroup.id == account_models.UserGroupMember.group_id,
            account_models.UserGroup.amo_id == amo_id,
            account_models.UserGroup.is_active.is_(True),
        ))
    if filters.contract_type:
        query = query.filter(_chosen_contract_match(
            amo_id=amo_id,
            today=today,
            conditions=[models.EmploymentContract.contract_type == filters.contract_type],
        ))
    if filters.employment_status:
        query = query.filter(_chosen_contract_match(
            amo_id=amo_id,
            today=today,
            conditions=[models.EmploymentContract.employment_status == filters.employment_status],
        ))
    if filters.base_station_id:
        query = query.filter(_chosen_contract_match(
            amo_id=amo_id,
            today=today,
            conditions=[models.EmploymentContract.primary_base_station_id == filters.base_station_id],
        ))
    if filters.expires_within_days:
        cutoff = today + timedelta(days=filters.expires_within_days)
        query = query.filter(_chosen_contract_match(
            amo_id=amo_id,
            today=today,
            conditions=[
                models.EmploymentContract.effective_to.is_not(None),
                models.EmploymentContract.effective_to >= today,
                models.EmploymentContract.effective_to <= cutoff,
            ],
        ))

    if filters.contract_state == "EFFECTIVE":
        query = query.filter(effective_exists)
    elif filters.contract_state == "FUTURE":
        query = query.filter(~effective_exists, future_exists)
    elif filters.contract_state == "MISSING":
        query = query.filter(~effective_exists, ~future_exists)

    if filters.pattern_state == "DEFAULT":
        query = query.filter(default_pattern)
    elif filters.pattern_state == "ASSIGNED":
        assigned = and_(active_pattern, ~default_pattern)
        query = query.filter(or_(assigned, automatic_pattern) if automatic_pattern is not None else assigned)
    elif filters.pattern_state == "MISSING":
        query = query.filter(
            and_(~active_pattern, ~automatic_pattern)
            if automatic_pattern is not None
            else ~active_pattern
        )

    if filters.readiness_state == "READY":
        query = query.filter(ready, ~blocked)
    elif filters.readiness_state == "BLOCKED":
        query = query.filter(blocked)
    elif filters.readiness_state == "NEEDS_ATTENTION":
        query = query.filter(~blocked, ~ready)

    return query


def _apply_sort(query, *, filters: hr_schemas.HrPeopleFilterInput):
    direction = "desc" if filters.sort_dir == "desc" else "asc"
    if filters.sort_by == "staff_code":
        expression = account_models.User.staff_code
    elif filters.sort_by == "role":
        expression = account_models.User.role
    elif filters.sort_by == "position_title":
        expression = account_models.User.position_title
    elif filters.sort_by == "department":
        expression = account_models.Department.name
        query = query.outerjoin(
            account_models.Department,
            and_(
                account_models.Department.id == account_models.User.department_id,
                account_models.Department.amo_id == account_models.User.amo_id,
            ),
        )
    else:
        expression = account_models.User.full_name
    order = expression.desc() if direction == "desc" else expression.asc()
    return query.order_by(order, account_models.User.full_name.asc(), account_models.User.id.asc())


def _group_memberships(
    db: Session,
    *,
    amo_id: str,
    user_ids: list[str],
) -> dict[str, list[tuple[str, str]]]:
    result: dict[str, list[tuple[str, str]]] = defaultdict(list)
    if not user_ids:
        return result
    rows = db.query(
        account_models.UserGroupMember.user_id,
        account_models.UserGroup.id,
        account_models.UserGroup.name,
    ).join(
        account_models.UserGroup,
        account_models.UserGroup.id == account_models.UserGroupMember.group_id,
    ).filter(
        account_models.UserGroup.amo_id == amo_id,
        account_models.UserGroup.is_active.is_(True),
        account_models.UserGroupMember.user_id.in_(user_ids),
    ).order_by(
        account_models.UserGroupMember.user_id.asc(),
        account_models.UserGroup.name.asc(),
        account_models.UserGroup.id.asc(),
    ).all()
    for user_id, group_id, group_name in rows:
        result[str(user_id)].append((str(group_id), str(group_name)))
    return result


def _serialize_users(
    db: Session,
    *,
    amo_id: str,
    users: list[account_models.User],
    today: date,
    now: datetime,
) -> list[hr_schemas.HrPersonReadiness]:
    user_ids = [str(user.id) for user in users]
    contracts = hr_service._readiness_contracts_by_user(
        db,
        amo_id=amo_id,
        user_ids=user_ids,
        on_date=today,
    )
    patterns = hr_service._effective_patterns(
        db,
        amo_id=amo_id,
        user_ids=user_ids,
        on_date=today,
    )
    leave_by_user = hr_service._active_leave(
        db,
        amo_id=amo_id,
        user_ids=user_ids,
        now=now,
    )
    hire_dates = services.hire_dates_by_user(db, amo_id=amo_id, user_ids=user_ids)
    memberships = _group_memberships(db, amo_id=amo_id, user_ids=user_ids)
    managed_pattern_id = hr_service._default_day_system_id(
        amo_id=amo_id,
        system_key=hr_service._DEFAULT_DAY_PATTERN_KEY,
    )

    items: list[hr_schemas.HrPersonReadiness] = []
    for user in users:
        user_id = str(user.id)
        contract = contracts.get(user_id)
        pattern = patterns.get(user_id)
        item = hr_service._person_readiness_for_user(
            user,
            amo_id=amo_id,
            contract=contract,
            pattern=pattern,
            leave=leave_by_user.get(user_id),
            on_date=today,
            hire_date=hire_dates.get(user_id),
        )
        contract_state = "MISSING"
        if contract:
            contract_state = (
                "EFFECTIVE"
                if contract.effective_from <= today
                and (contract.effective_to is None or contract.effective_to >= today)
                else "FUTURE"
            )
        pattern_state = "MISSING"
        if pattern and pattern.work_pattern and pattern.work_pattern.is_active:
            pattern_state = (
                "DEFAULT"
                if str(pattern.work_pattern_id) == managed_pattern_id
                else "ASSIGNED"
            )
        groups = memberships.get(user_id, [])
        department = getattr(user, "department", None)
        items.append(item.model_copy(update={
            "account_role": hr_service._value(user.role),
            "department_id": str(user.department_id) if user.department_id else None,
            "department_code": getattr(department, "code", None),
            "department_name": getattr(department, "name", None),
            "contract_state": contract_state,
            "pattern_state": pattern_state,
            "group_ids": [group_id for group_id, _ in groups],
            "group_names": [group_name for _, group_name in groups],
        }))
    hr_service._apply_automatic_pattern_readiness(
        db,
        amo_id=amo_id,
        on_date=today,
        items=items,
    )
    return items


def list_people_page(
    db: Session,
    *,
    amo_id: str,
    page: int,
    page_size: int,
    filters: hr_schemas.HrPeopleFilterInput,
) -> hr_schemas.HrPeoplePage:
    today = _today(db, amo_id=amo_id)
    now = hr_service._utcnow()
    safe_page_size = max(1, min(int(page_size), 200))
    safe_page = max(1, int(page))
    automatic_ids: set[str] = set()
    ambiguous_ids: set[str] = set()
    if filters.pattern_state or filters.readiness_state:
        automatic_ids, ambiguous_ids = _automatic_pattern_resolution(
            db,
            amo_id=amo_id,
            today=today,
        )

    query = _apply_filters(
        _base_user_query(db, amo_id=amo_id),
        amo_id=amo_id,
        filters=filters,
        today=today,
        now=now,
        automatic_patterned_user_ids=automatic_ids,
        ambiguous_pattern_user_ids=ambiguous_ids,
    )
    total = int(query.order_by(None).count())
    pages = (total + safe_page_size - 1) // safe_page_size if total else 0
    if pages and safe_page > pages:
        safe_page = pages
    users = _apply_sort(query, filters=filters).options(
        joinedload(account_models.User.department),
    ).offset((safe_page - 1) * safe_page_size).limit(safe_page_size).all()

    return hr_schemas.HrPeoplePage(
        items=_serialize_users(
            db,
            amo_id=amo_id,
            users=users,
            today=today,
            now=now,
        ),
        page=safe_page,
        page_size=safe_page_size,
        total=total,
        pages=pages,
    )


def _options(rows, *, value_index: int = 0, label_index: int = 1, count_index: int = 2):
    return [
        hr_schemas.HrFilterOption(
            value=str(row[value_index]),
            label=str(row[label_index]),
            count=int(row[count_index] or 0),
        )
        for row in rows
        if row[value_index] is not None and str(row[value_index]).strip()
    ]


def list_people_facets(db: Session, *, amo_id: str) -> hr_schemas.HrPeopleFacets:
    today = _today(db, amo_id=amo_id)
    now = hr_service._utcnow()
    automatic_ids, ambiguous_ids = _automatic_pattern_resolution(
        db,
        amo_id=amo_id,
        today=today,
    )
    human_filter = (
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )

    departments = db.query(
        account_models.Department.id,
        account_models.Department.name,
        func.count(account_models.User.id),
    ).join(
        account_models.User,
        account_models.User.department_id == account_models.Department.id,
    ).filter(
        account_models.Department.amo_id == amo_id,
        *human_filter,
    ).group_by(
        account_models.Department.id,
        account_models.Department.name,
    ).order_by(account_models.Department.name.asc()).all()

    roles = db.query(
        account_models.User.role,
        func.count(account_models.User.id),
    ).filter(*human_filter).group_by(account_models.User.role).order_by(account_models.User.role.asc()).all()
    role_options = [
        hr_schemas.HrFilterOption(
            value=hr_service._value(role),
            label=hr_service._value(role).replace("_", " ").title(),
            count=int(count or 0),
        )
        for role, count in roles
    ]

    positions = db.query(
        account_models.User.position_title,
        func.count(account_models.User.id),
    ).filter(
        *human_filter,
        account_models.User.position_title.is_not(None),
        func.length(func.trim(account_models.User.position_title)) > 0,
    ).group_by(account_models.User.position_title).order_by(account_models.User.position_title.asc()).limit(250).all()
    position_options = [
        hr_schemas.HrFilterOption(value=str(title), label=str(title), count=int(count or 0))
        for title, count in positions
    ]

    groups = db.query(
        account_models.UserGroup.id,
        account_models.UserGroup.name,
        func.count(func.distinct(account_models.UserGroupMember.user_id)),
    ).join(
        account_models.UserGroupMember,
        account_models.UserGroupMember.group_id == account_models.UserGroup.id,
    ).join(
        account_models.User,
        account_models.User.id == account_models.UserGroupMember.user_id,
    ).filter(
        account_models.UserGroup.amo_id == amo_id,
        account_models.UserGroup.is_active.is_(True),
        *human_filter,
    ).group_by(account_models.UserGroup.id, account_models.UserGroup.name).order_by(account_models.UserGroup.name.asc()).all()

    candidate_contract = or_(
        and_(
            models.EmploymentContract.effective_from <= today,
            or_(
                models.EmploymentContract.effective_to.is_(None),
                models.EmploymentContract.effective_to >= today,
            ),
        ),
        models.EmploymentContract.effective_from > today,
    )
    contract_filter = (
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.employment_status.in_([
            models.EmploymentStatus.ACTIVE,
            models.EmploymentStatus.ONBOARDING,
            models.EmploymentStatus.SUSPENDED,
        ]),
        candidate_contract,
    )
    contract_types = db.query(
        models.EmploymentContract.contract_type,
        func.count(func.distinct(models.EmploymentContract.user_id)),
    ).filter(*contract_filter).group_by(models.EmploymentContract.contract_type).order_by(models.EmploymentContract.contract_type.asc()).all()
    employment_statuses = db.query(
        models.EmploymentContract.employment_status,
        func.count(func.distinct(models.EmploymentContract.user_id)),
    ).filter(*contract_filter).group_by(models.EmploymentContract.employment_status).order_by(models.EmploymentContract.employment_status.asc()).all()
    bases = db.query(
        foundation_models.BaseStation.id,
        foundation_models.BaseStation.name,
        func.count(func.distinct(models.EmploymentContract.user_id)),
    ).join(
        models.EmploymentContract,
        models.EmploymentContract.primary_base_station_id == foundation_models.BaseStation.id,
    ).filter(
        foundation_models.BaseStation.amo_id == amo_id,
        *contract_filter,
    ).group_by(foundation_models.BaseStation.id, foundation_models.BaseStation.name).order_by(foundation_models.BaseStation.name.asc()).all()

    def count_for(**updates) -> int:
        model = hr_schemas.HrPeopleFilterInput(**updates)
        return int(_apply_filters(
            _base_user_query(db, amo_id=amo_id),
            amo_id=amo_id,
            filters=model,
            today=today,
            now=now,
            automatic_patterned_user_ids=automatic_ids,
            ambiguous_pattern_user_ids=ambiguous_ids,
        ).order_by(None).count())

    readiness_states = [
        hr_schemas.HrFilterOption(value=value, label=label, count=count_for(readiness_state=value))
        for value, label in (
            ("READY", "Ready"),
            ("NEEDS_ATTENTION", "Needs attention"),
            ("BLOCKED", "Blocked"),
        )
    ]
    contract_states = [
        hr_schemas.HrFilterOption(value=value, label=label, count=count_for(contract_state=value))
        for value, label in (
            ("EFFECTIVE", "Effective contract"),
            ("FUTURE", "Future contract"),
            ("MISSING", "No contract"),
        )
    ]
    pattern_states = [
        hr_schemas.HrFilterOption(value=value, label=label, count=count_for(pattern_state=value))
        for value, label in (
            ("DEFAULT", "Legacy default"),
            ("ASSIGNED", "Assigned or automatic"),
            ("MISSING", "No matching pattern"),
        )
    ]

    return hr_schemas.HrPeopleFacets(
        departments=_options(departments),
        roles=role_options,
        position_titles=position_options,
        contract_types=[
            hr_schemas.HrFilterOption(
                value=hr_service._value(value),
                label=hr_service._value(value).replace("_", " ").title(),
                count=int(count or 0),
            )
            for value, count in contract_types
        ],
        employment_statuses=[
            hr_schemas.HrFilterOption(
                value=hr_service._value(value),
                label=hr_service._value(value).replace("_", " ").title(),
                count=int(count or 0),
            )
            for value, count in employment_statuses
        ],
        bases=_options(bases),
        groups=_options(groups),
        readiness_states=readiness_states,
        contract_states=contract_states,
        pattern_states=pattern_states,
    )


def resolve_selection_user_ids(
    db: Session,
    *,
    amo_id: str,
    selection: hr_schemas.HrPeopleSelection,
) -> list[str]:
    today = _today(db, amo_id=amo_id)
    now = hr_service._utcnow()
    query = _base_user_query(db, amo_id=amo_id)
    if selection.mode == "EXPLICIT":
        query = query.filter(account_models.User.id.in_(selection.user_ids))
    else:
        automatic_ids: set[str] = set()
        ambiguous_ids: set[str] = set()
        if selection.filters.pattern_state or selection.filters.readiness_state:
            automatic_ids, ambiguous_ids = _automatic_pattern_resolution(
                db,
                amo_id=amo_id,
                today=today,
            )
        query = _apply_filters(
            query,
            amo_id=amo_id,
            filters=selection.filters,
            today=today,
            now=now,
            automatic_patterned_user_ids=automatic_ids,
            ambiguous_pattern_user_ids=ambiguous_ids,
        )
        if selection.exclude_user_ids:
            query = query.filter(account_models.User.id.notin_(selection.exclude_user_ids))
    count = int(query.order_by(None).count())
    if count > MAX_BATCH_USERS:
        raise ValueError(
            f"This batch matches {count} users; narrow the filters to {MAX_BATCH_USERS} or fewer."
        )
    return [
        str(user_id)
        for (user_id,) in query.with_entities(account_models.User.id).order_by(
            account_models.User.full_name.asc(),
            account_models.User.id.asc(),
        ).all()
    ]


def preview_default_day_pattern_batch(
    db: Session,
    *,
    amo_id: str,
    selection: hr_schemas.HrPeopleSelection,
) -> hr_schemas.HrDefaultDayBatchPreview:
    user_ids = resolve_selection_user_ids(db, amo_id=amo_id, selection=selection)
    if not user_ids:
        return hr_schemas.HrDefaultDayBatchPreview(
            matched_count=0,
            eligible_count=0,
            assignable_count=0,
            already_assigned_count=0,
            ineligible_count=0,
        )
    today = _today(db, amo_id=amo_id)
    eligible_ids = {
        str(user_id)
        for (user_id,) in db.query(models.EmploymentContract.user_id).filter(
            models.EmploymentContract.amo_id == amo_id,
            models.EmploymentContract.user_id.in_(user_ids),
            models.EmploymentContract.employment_status.in_([
                models.EmploymentStatus.ACTIVE,
                models.EmploymentStatus.ONBOARDING,
            ]),
            models.EmploymentContract.effective_from <= today,
            or_(
                models.EmploymentContract.effective_to.is_(None),
                models.EmploymentContract.effective_to >= today,
            ),
        ).distinct().all()
    }
    assigned_ids = {
        str(user_id)
        for (user_id,) in db.query(models.EmployeeWorkPatternAssignment.user_id).join(
            models.WorkPattern,
            models.WorkPattern.id == models.EmployeeWorkPatternAssignment.work_pattern_id,
        ).filter(
            models.EmployeeWorkPatternAssignment.amo_id == amo_id,
            models.EmployeeWorkPatternAssignment.user_id.in_(list(eligible_ids) or ["__none__"]),
            models.EmployeeWorkPatternAssignment.effective_from <= today,
            or_(
                models.EmployeeWorkPatternAssignment.effective_to.is_(None),
                models.EmployeeWorkPatternAssignment.effective_to >= today,
            ),
            models.WorkPattern.amo_id == amo_id,
            models.WorkPattern.is_active.is_(True),
        ).distinct().all()
    }
    return hr_schemas.HrDefaultDayBatchPreview(
        matched_count=len(user_ids),
        eligible_count=len(eligible_ids),
        assignable_count=len(eligible_ids - assigned_ids),
        already_assigned_count=len(assigned_ids),
        ineligible_count=len(user_ids) - len(eligible_ids),
    )


def _ensure_default_day_entities(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    operation_id: str,
):
    amo = db.query(account_models.AMO).filter(
        account_models.AMO.id == amo_id,
    ).with_for_update().one()
    timezone_name = str(amo.time_zone or "UTC")

    shift = hr_service._resolve_existing_day_shift(db, amo_id=amo_id)

    pattern_id = hr_service._default_day_system_id(
        amo_id=amo_id,
        system_key=hr_service._DEFAULT_DAY_PATTERN_KEY,
    )
    pattern_by_code = db.query(models.WorkPattern).filter(
        models.WorkPattern.amo_id == amo_id,
        models.WorkPattern.code == hr_service._DEFAULT_DAY_PATTERN_CODE,
    ).with_for_update().first()
    pattern = db.query(models.WorkPattern).filter(
        models.WorkPattern.amo_id == amo_id,
        models.WorkPattern.id == pattern_id,
    ).with_for_update().first()
    if pattern_by_code is not None and str(pattern_by_code.id) != pattern_id:
        raise ValueError(
            "Reserved work-pattern code DEFAULT-DAY-5X2 is already owned by tenant configuration; "
            "rename that pattern before applying the managed default-day baseline."
        )
    if pattern is not None and pattern_by_code is not None and str(pattern.id) != str(pattern_by_code.id):
        raise ValueError("Managed default-day pattern identity conflicts with the reserved code")

    pattern_before = hr_service._work_pattern_snapshot(db, pattern) if pattern is not None else None
    if pattern is None:
        pattern = models.WorkPattern(
            id=pattern_id,
            amo_id=amo_id,
            code=hr_service._DEFAULT_DAY_PATTERN_CODE,
            name="Default day shift · Monday to Friday",
            description=(
                "Portal-managed five-day baseline followed by two days off. "
                "This is visible draft input, not a published roster."
            ),
            cycle_length_days=7,
            is_active=True,
            timezone_name=timezone_name,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(pattern)
        db.flush()
    else:
        pattern.code = hr_service._DEFAULT_DAY_PATTERN_CODE
        pattern.name = "Default day shift · Monday to Friday"
        pattern.description = (
            "Portal-managed five-day baseline followed by two days off. "
            "This is visible draft input, not a published roster."
        )
        pattern.cycle_length_days = 7
        pattern.is_active = True
        pattern.timezone_name = timezone_name
        pattern.updated_by_user_id = actor_user_id
        db.add(pattern)
        db.flush()

    existing_days = db.query(models.WorkPatternDay).filter(
        models.WorkPatternDay.amo_id == amo_id,
        models.WorkPatternDay.work_pattern_id == pattern.id,
    ).order_by(models.WorkPatternDay.cycle_day_index.asc(), models.WorkPatternDay.id.asc()).all()
    days_by_index = {
        int(row.cycle_day_index): row
        for row in existing_days
        if 0 <= int(row.cycle_day_index) < 7
    }
    for extra_day in existing_days:
        if int(extra_day.cycle_day_index) not in range(7):
            db.delete(extra_day)
    for day_index in range(7):
        duty = day_index < 5
        day = days_by_index.get(day_index)
        if day is None:
            day = models.WorkPatternDay(
                amo_id=amo_id,
                work_pattern_id=pattern.id,
                cycle_day_index=day_index,
            )
        day.shift_template_id = shift.id if duty else None
        day.status = models.PatternDayStatus.DUTY if duty else models.PatternDayStatus.OFF
        day.start_time_local = "08:00" if duty else None
        day.end_time_local = "17:00" if duty else None
        day.spans_next_day = False
        day.planned_minutes = 480 if duty else 0
        db.add(day)
    db.flush()

    pattern_after = hr_service._work_pattern_snapshot(db, pattern)
    if pattern_before != pattern_after:
        hr_service._bootstrap_audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            entity_type="WorkPattern",
            entity_id=str(pattern.id),
            action="bootstrap_create" if pattern_before is None else "bootstrap_update",
            before=pattern_before,
            after=pattern_after,
            metadata={"system_key": hr_service._DEFAULT_DAY_PATTERN_KEY},
        )
    return shift, pattern


def apply_default_day_pattern_batch(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: hr_schemas.HrDefaultDayBatchApplyRequest,
) -> hr_schemas.HrDefaultDayBatchResult:
    user_ids = resolve_selection_user_ids(db, amo_id=amo_id, selection=payload.selection)
    if len(user_ids) != payload.expected_match_count:
        raise ValueError(
            "The filtered population changed after preview. Review the updated count before applying the pattern."
        )
    operation_id = hr_service.uuid4().hex
    today = _today(db, amo_id=amo_id)
    week_monday = today - timedelta(days=today.weekday())
    shift, pattern = _ensure_default_day_entities(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        operation_id=operation_id,
    )

    eligible_user_ids = {
        str(user_id)
        for (user_id,) in db.query(models.EmploymentContract.user_id).filter(
            models.EmploymentContract.amo_id == amo_id,
            models.EmploymentContract.user_id.in_(user_ids or ["__none__"]),
            models.EmploymentContract.employment_status.in_([
                models.EmploymentStatus.ACTIVE,
                models.EmploymentStatus.ONBOARDING,
            ]),
            models.EmploymentContract.effective_from <= today,
            or_(
                models.EmploymentContract.effective_to.is_(None),
                models.EmploymentContract.effective_to >= today,
            ),
        ).distinct().all()
    }
    eligible_users = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id.in_(list(eligible_user_ids) or ["__none__"]),
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(account_models.User.full_name.asc(), account_models.User.id.asc()).all()

    current_rows = db.query(models.EmployeeWorkPatternAssignment).options(
        joinedload(models.EmployeeWorkPatternAssignment.work_pattern),
    ).filter(
        models.EmployeeWorkPatternAssignment.amo_id == amo_id,
        models.EmployeeWorkPatternAssignment.user_id.in_(list(eligible_user_ids) or ["__none__"]),
        models.EmployeeWorkPatternAssignment.effective_from <= today,
        or_(
            models.EmployeeWorkPatternAssignment.effective_to.is_(None),
            models.EmployeeWorkPatternAssignment.effective_to >= today,
        ),
    ).with_for_update(of=models.EmployeeWorkPatternAssignment).all()
    current_by_user = {str(row.user_id): row for row in current_rows}

    future_rows = db.query(models.EmployeeWorkPatternAssignment).filter(
        models.EmployeeWorkPatternAssignment.amo_id == amo_id,
        models.EmployeeWorkPatternAssignment.user_id.in_(list(eligible_user_ids) or ["__none__"]),
        models.EmployeeWorkPatternAssignment.effective_from > today,
    ).order_by(
        models.EmployeeWorkPatternAssignment.user_id.asc(),
        models.EmployeeWorkPatternAssignment.effective_from.asc(),
        models.EmployeeWorkPatternAssignment.id.asc(),
    ).with_for_update(of=models.EmployeeWorkPatternAssignment).all()
    future_by_user: dict[str, models.EmployeeWorkPatternAssignment] = {}
    for row in future_rows:
        future_by_user.setdefault(str(row.user_id), row)

    assigned = 0
    already_assigned = 0
    skipped_conflict = 0
    for user in eligible_users:
        user_id = str(user.id)
        current = current_by_user.get(user_id)
        current_has_active_pattern = bool(
            current and current.work_pattern and current.work_pattern.is_active
        )
        current_is_default = bool(
            current_has_active_pattern and str(current.work_pattern_id) == str(pattern.id)
        )
        default_anchor_is_monday = bool(
            current_is_default
            and current.cycle_anchor_date
            and current.cycle_anchor_date.weekday() == 0
        )
        if current_has_active_pattern and (
            not current_is_default or default_anchor_is_monday
        ):
            already_assigned += 1
            continue

        future = future_by_user.get(user_id)
        effective_to = future.effective_from - timedelta(days=1) if future else None
        if effective_to is not None and effective_to < today:
            skipped_conflict += 1
            continue

        if current is not None:
            before = hr_service._pattern_assignment_snapshot(current)
            if current.effective_from < today:
                current.effective_to = today - timedelta(days=1)
                db.add(current)
                db.flush()
                hr_service._bootstrap_audit(
                    db,
                    amo_id=amo_id,
                    actor_user_id=actor_user_id,
                    operation_id=operation_id,
                    entity_type="EmployeeWorkPatternAssignment",
                    entity_id=str(current.id),
                    action="bootstrap_close",
                    before=before,
                    after=hr_service._pattern_assignment_snapshot(current),
                    metadata={"user_id": user_id, "replacement_pattern_id": str(pattern.id)},
                )
            else:
                current_id = str(current.id)
                db.delete(current)
                db.flush()
                hr_service._bootstrap_audit(
                    db,
                    amo_id=amo_id,
                    actor_user_id=actor_user_id,
                    operation_id=operation_id,
                    entity_type="EmployeeWorkPatternAssignment",
                    entity_id=current_id,
                    action="bootstrap_replace",
                    before=before,
                    metadata={"user_id": user_id, "replacement_pattern_id": str(pattern.id)},
                )

        created = models.EmployeeWorkPatternAssignment(
            amo_id=amo_id,
            user_id=user_id,
            work_pattern_id=pattern.id,
            effective_from=today,
            effective_to=effective_to,
            cycle_anchor_date=week_monday,
            created_by_user_id=actor_user_id,
        )
        db.add(created)
        db.flush()
        hr_service._bootstrap_audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            entity_type="EmployeeWorkPatternAssignment",
            entity_id=str(created.id),
            action="bootstrap_assign",
            after=hr_service._pattern_assignment_snapshot(created),
            metadata={"user_id": user_id, "system_key": hr_service._DEFAULT_DAY_PATTERN_KEY},
        )
        assigned += 1

    db.flush()
    return hr_schemas.HrDefaultDayBatchResult(
        shift_template_id=str(shift.id),
        work_pattern_id=str(pattern.id),
        matched_count=len(user_ids),
        eligible_count=len(eligible_user_ids),
        assigned_count=assigned,
        already_assigned_count=already_assigned,
        ineligible_count=len(user_ids) - len(eligible_user_ids),
        skipped_conflict_count=skipped_conflict,
    )


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def export_people_csv(
    db: Session,
    *,
    amo_id: str,
    selection: hr_schemas.HrPeopleSelection,
) -> str:
    user_ids = resolve_selection_user_ids(db, amo_id=amo_id, selection=selection)
    today = _today(db, amo_id=amo_id)
    now = hr_service._utcnow()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Staff code",
        "Full name",
        "Email",
        "Portal role",
        "Position title",
        "Department",
        "Groups",
        "Contract state",
        "Employment status",
        "Contract type",
        "Contract effective from",
        "Contract effective to",
        "Primary base",
        "Work pattern",
        "Pattern state",
        "Readiness",
        "Readiness reasons",
        "Payroll number",
        "Cost centre",
        "FTE percentage",
    ])
    for start in range(0, len(user_ids), _BATCH_CHUNK_SIZE):
        chunk = user_ids[start:start + _BATCH_CHUNK_SIZE]
        users = _base_user_query(db, amo_id=amo_id).filter(
            account_models.User.id.in_(chunk),
        ).options(joinedload(account_models.User.department)).order_by(
            account_models.User.full_name.asc(),
            account_models.User.id.asc(),
        ).all()
        for item in _serialize_users(
            db,
            amo_id=amo_id,
            users=users,
            today=today,
            now=now,
        ):
            writer.writerow([
                _csv_safe(item.staff_code),
                _csv_safe(item.full_name),
                _csv_safe(item.email),
                _csv_safe(item.account_role),
                _csv_safe(item.position_title),
                _csv_safe(item.department_name or item.department_code),
                _csv_safe("; ".join(item.group_names)),
                item.contract_state,
                _csv_safe(item.employment_status),
                _csv_safe(item.contract_type),
                _csv_safe(item.contract_effective_from),
                _csv_safe(item.contract_effective_to),
                _csv_safe(item.primary_base_code),
                _csv_safe(item.work_pattern_code),
                item.pattern_state,
                item.readiness_state,
                _csv_safe("; ".join(item.readiness_reasons)),
                _csv_safe(item.payroll_number),
                _csv_safe(item.cost_centre),
                item.fte_percentage,
            ])
    return output.getvalue()
