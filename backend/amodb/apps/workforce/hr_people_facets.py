"""Consistent facet counts for the scalable Workforce people directory."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..foundations import models as foundation_models
from . import hr_people_directory, hr_schemas, hr_service, models


def list_people_facets(db: Session, *, amo_id: str) -> hr_schemas.HrPeopleFacets:
    today = hr_people_directory._today(db, amo_id=amo_id)
    now = hr_service._utcnow()
    automatic_ids, ambiguous_ids = hr_people_directory._automatic_pattern_resolution(
        db,
        amo_id=amo_id,
        today=today,
    )
    human_filter = (
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )

    def count_for(**updates) -> int:
        filters = hr_schemas.HrPeopleFilterInput(**updates)
        query = hr_people_directory._apply_filters(
            hr_people_directory._base_user_query(db, amo_id=amo_id),
            amo_id=amo_id,
            filters=filters,
            today=today,
            now=now,
            automatic_patterned_user_ids=automatic_ids,
            ambiguous_pattern_user_ids=ambiguous_ids,
        )
        return int(query.order_by(None).count())

    departments = db.query(
        account_models.Department.id,
        account_models.Department.name,
        func.count(account_models.User.id),
    ).join(
        account_models.User,
        account_models.User.department_id == account_models.Department.id,
    ).filter(
        account_models.Department.amo_id == amo_id,
        account_models.Department.is_active.is_(True),
        *human_filter,
    ).group_by(
        account_models.Department.id,
        account_models.Department.name,
    ).order_by(account_models.Department.name.asc()).all()

    roles = db.query(
        account_models.User.role,
        func.count(account_models.User.id),
    ).filter(*human_filter).group_by(
        account_models.User.role,
    ).order_by(account_models.User.role.asc()).all()

    position_titles = db.query(
        account_models.User.position_title,
        func.count(account_models.User.id),
    ).filter(
        *human_filter,
        account_models.User.position_title.is_not(None),
        func.length(func.trim(account_models.User.position_title)) > 0,
    ).group_by(
        account_models.User.position_title,
    ).order_by(
        func.count(account_models.User.id).desc(),
        account_models.User.position_title.asc(),
    ).limit(500).all()

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
    ).group_by(
        account_models.UserGroup.id,
        account_models.UserGroup.name,
    ).order_by(account_models.UserGroup.name.asc()).all()

    bases = db.query(
        foundation_models.BaseStation.id,
        foundation_models.BaseStation.name,
    ).filter(
        foundation_models.BaseStation.amo_id == amo_id,
        foundation_models.BaseStation.is_active.is_(True),
    ).order_by(foundation_models.BaseStation.name.asc()).all()

    contract_type_options = []
    for contract_type in models.ContractType:
        value = hr_service._value(contract_type)
        count = count_for(contract_type=value)
        if count:
            contract_type_options.append(hr_schemas.HrFilterOption(
                value=value,
                label=value.replace("_", " ").title(),
                count=count,
            ))

    employment_status_options = []
    for employment_status in (
        models.EmploymentStatus.ACTIVE,
        models.EmploymentStatus.ONBOARDING,
        models.EmploymentStatus.SUSPENDED,
    ):
        value = hr_service._value(employment_status)
        count = count_for(employment_status=value)
        if count:
            employment_status_options.append(hr_schemas.HrFilterOption(
                value=value,
                label=value.replace("_", " ").title(),
                count=count,
            ))

    base_options = []
    for base_id, base_name in bases:
        count = count_for(base_station_id=str(base_id))
        if count:
            base_options.append(hr_schemas.HrFilterOption(
                value=str(base_id),
                label=str(base_name),
                count=count,
            ))

    def static_options(field: str, values: tuple[tuple[str, str], ...]):
        return [
            hr_schemas.HrFilterOption(
                value=value,
                label=label,
                count=count_for(**{field: value}),
            )
            for value, label in values
        ]

    return hr_schemas.HrPeopleFacets(
        departments=[
            hr_schemas.HrFilterOption(value=str(value), label=str(label), count=int(count or 0))
            for value, label, count in departments
        ],
        roles=[
            hr_schemas.HrFilterOption(
                value=hr_service._value(value),
                label=hr_service._value(value).replace("_", " ").title(),
                count=int(count or 0),
            )
            for value, count in roles
        ],
        position_titles=[
            hr_schemas.HrFilterOption(value=str(value), label=str(value), count=int(count or 0))
            for value, count in position_titles
        ],
        contract_types=contract_type_options,
        employment_statuses=employment_status_options,
        bases=base_options,
        groups=[
            hr_schemas.HrFilterOption(value=str(value), label=str(label), count=int(count or 0))
            for value, label, count in groups
        ],
        readiness_states=static_options("readiness_state", (
            ("READY", "Ready"),
            ("NEEDS_ATTENTION", "Needs attention"),
            ("BLOCKED", "Blocked"),
        )),
        contract_states=static_options("contract_state", (
            ("EFFECTIVE", "Effective contract"),
            ("FUTURE", "Future contract"),
            ("MISSING", "No contract"),
        )),
        pattern_states=static_options("pattern_state", (
            ("DEFAULT", "Legacy default"),
            ("ASSIGNED", "Assigned or automatic"),
            ("MISSING", "No matching pattern"),
        )),
    )
