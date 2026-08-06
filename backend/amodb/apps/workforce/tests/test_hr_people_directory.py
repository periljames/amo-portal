from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.foundations import models as foundation_models
from amodb.apps.workforce import (
    hr_people_directory,
    hr_schemas,
    hr_selection_integrity,
    hr_service,
    models,
)


def _id() -> str:
    return str(uuid4())


def _postgres_session() -> tuple[object, object, object, Session]:
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, autoflush=False, expire_on_commit=False)
    return engine, connection, transaction, db


def _close_postgres_session(engine, connection, transaction, db: Session) -> None:
    db.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()
    engine.dispose()


def _seed_directory(db: Session) -> dict[str, str]:
    today = date.today()
    amo_id = _id()
    engineering_id = _id()
    quality_id = _id()
    base_id = _id()
    engineering_group_id = _id()

    db.add(
        account_models.AMO(
            id=amo_id,
            amo_code=f"DIR-{amo_id[:8]}",
            name="Workforce Directory Test",
            login_slug=f"directory-{amo_id[:8]}",
            time_zone="UTC",
        )
    )
    db.flush()

    db.add_all([
        account_models.Department(
            id=engineering_id,
            amo_id=amo_id,
            code="ENG",
            name="Engineering",
            is_active=True,
        ),
        account_models.Department(
            id=quality_id,
            amo_id=amo_id,
            code="QMS",
            name="Quality",
            is_active=True,
        ),
    ])
    db.add(
        foundation_models.BaseStation(
            id=base_id,
            amo_id=amo_id,
            code="NBO",
            name="Nairobi Main Base",
            base_type=foundation_models.BaseStationType.MAIN_BASE,
            is_active=True,
        )
    )
    db.flush()

    users = {
        "alice": account_models.User(
            id=_id(),
            amo_id=amo_id,
            department_id=engineering_id,
            staff_code="E001",
            email="alice@directory.invalid",
            first_name="Alice",
            last_name="Engineer",
            full_name="Alice Engineer",
            position_title="Licensed Aircraft Engineer",
            role=account_models.AccountRole.CERTIFYING_ENGINEER,
            hashed_password="not-a-real-password-hash",
            is_active=True,
            is_system_account=False,
        ),
        "brian": account_models.User(
            id=_id(),
            amo_id=amo_id,
            department_id=engineering_id,
            staff_code="E002",
            email="brian@directory.invalid",
            first_name="Brian",
            last_name="Technician",
            full_name="Brian Technician",
            position_title="Aircraft Technician",
            role=account_models.AccountRole.TECHNICIAN,
            hashed_password="not-a-real-password-hash",
            is_active=True,
            is_system_account=False,
        ),
        "carol": account_models.User(
            id=_id(),
            amo_id=amo_id,
            department_id=quality_id,
            staff_code="Q001",
            email="carol@directory.invalid",
            first_name="Carol",
            last_name="Inspector",
            full_name="Carol Inspector",
            position_title="Quality Inspector",
            role=account_models.AccountRole.QUALITY_INSPECTOR,
            hashed_password="not-a-real-password-hash",
            is_active=True,
            is_system_account=False,
        ),
        "david": account_models.User(
            id=_id(),
            amo_id=amo_id,
            department_id=quality_id,
            staff_code="Q002",
            email="david@directory.invalid",
            first_name="David",
            last_name="Auditor",
            full_name="David Auditor",
            position_title="Quality Auditor",
            role=account_models.AccountRole.AUDITOR,
            hashed_password="not-a-real-password-hash",
            is_active=True,
            is_system_account=False,
        ),
    }
    db.add_all(users.values())
    db.flush()

    db.add(
        account_models.UserGroup(
            id=engineering_group_id,
            amo_id=amo_id,
            code="ENG-DUTY",
            name="Engineering Duty Team",
            group_type=account_models.UserGroupType.CUSTOM,
            is_active=True,
        )
    )
    db.flush()
    db.add_all([
        account_models.UserGroupMember(
            id=_id(),
            group_id=engineering_group_id,
            user_id=users["alice"].id,
            member_role="member",
        ),
        account_models.UserGroupMember(
            id=_id(),
            group_id=engineering_group_id,
            user_id=users["brian"].id,
            member_role="member",
        ),
    ])

    db.add_all([
        models.EmploymentContract(
            id=_id(),
            amo_id=amo_id,
            user_id=users["alice"].id,
            contract_type=models.ContractType.PERMANENT,
            employment_status=models.EmploymentStatus.ACTIVE,
            effective_from=today - timedelta(days=365),
            effective_to=None,
            standard_weekly_minutes=2400,
            standard_daily_minutes=480,
            fte_percentage=100,
            primary_base_station_id=base_id,
        ),
        models.EmploymentContract(
            id=_id(),
            amo_id=amo_id,
            user_id=users["brian"].id,
            contract_type=models.ContractType.CONTRACTOR,
            employment_status=models.EmploymentStatus.ONBOARDING,
            effective_from=today - timedelta(days=7),
            effective_to=today + timedelta(days=180),
            standard_weekly_minutes=2400,
            standard_daily_minutes=480,
            fte_percentage=100,
            primary_base_station_id=base_id,
        ),
        models.EmploymentContract(
            id=_id(),
            amo_id=amo_id,
            user_id=users["carol"].id,
            contract_type=models.ContractType.FIXED_TERM,
            employment_status=models.EmploymentStatus.ACTIVE,
            effective_from=today + timedelta(days=30),
            effective_to=today + timedelta(days=395),
            standard_weekly_minutes=2400,
            standard_daily_minutes=480,
            fte_percentage=100,
            primary_base_station_id=base_id,
        ),
    ])

    default_pattern_id = hr_service._default_day_system_id(
        amo_id=amo_id,
        system_key=hr_service._DEFAULT_DAY_PATTERN_KEY,
    )
    db.add(
        models.WorkPattern(
            id=default_pattern_id,
            amo_id=amo_id,
            code=hr_service._DEFAULT_DAY_PATTERN_CODE,
            name="Default day shift · Monday to Friday",
            cycle_length_days=7,
            is_active=True,
            timezone_name="UTC",
        )
    )
    db.flush()
    db.add(
        models.EmployeeWorkPatternAssignment(
            id=_id(),
            amo_id=amo_id,
            user_id=users["alice"].id,
            work_pattern_id=default_pattern_id,
            effective_from=today,
            effective_to=None,
            cycle_anchor_date=today - timedelta(days=today.weekday()),
        )
    )
    db.flush()

    return {
        "amo_id": amo_id,
        "engineering_id": engineering_id,
        "quality_id": quality_id,
        "base_id": base_id,
        "engineering_group_id": engineering_group_id,
        **{key: str(user.id) for key, user in users.items()},
    }


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL integration database is not configured",
)
def test_people_directory_filters_and_paginates_in_sql() -> None:
    engine, connection, transaction, db = _postgres_session()
    try:
        seeded = _seed_directory(db)

        first_page = hr_people_directory.list_people_page(
            db,
            amo_id=seeded["amo_id"],
            page=1,
            page_size=2,
            filters=hr_schemas.HrPeopleFilterInput(),
        )
        assert first_page.total == 4
        assert first_page.pages == 2
        assert [item.full_name for item in first_page.items] == [
            "Alice Engineer",
            "Brian Technician",
        ]

        engineering = hr_people_directory.list_people_page(
            db,
            amo_id=seeded["amo_id"],
            page=1,
            page_size=25,
            filters=hr_schemas.HrPeopleFilterInput(
                department_id=seeded["engineering_id"],
            ),
        )
        assert engineering.total == 2
        assert {item.account_role for item in engineering.items} == {
            "CERTIFYING_ENGINEER",
            "TECHNICIAN",
        }
        assert all(item.department_name == "Engineering" for item in engineering.items)
        assert engineering.items[0].group_names == ["Engineering Duty Team"]

        contractor = hr_people_directory.list_people_page(
            db,
            amo_id=seeded["amo_id"],
            page=1,
            page_size=25,
            filters=hr_schemas.HrPeopleFilterInput(contract_type="CONTRACTOR"),
        )
        assert [item.user_id for item in contractor.items] == [seeded["brian"]]

        future_contract = hr_people_directory.list_people_page(
            db,
            amo_id=seeded["amo_id"],
            page=1,
            page_size=25,
            filters=hr_schemas.HrPeopleFilterInput(contract_state="FUTURE"),
        )
        assert [item.user_id for item in future_contract.items] == [seeded["carol"]]
        assert future_contract.items[0].contract_state == "FUTURE"

        missing_contract = hr_people_directory.list_people_page(
            db,
            amo_id=seeded["amo_id"],
            page=1,
            page_size=25,
            filters=hr_schemas.HrPeopleFilterInput(contract_state="MISSING"),
        )
        assert [item.user_id for item in missing_contract.items] == [seeded["david"]]

        default_pattern = hr_people_directory.list_people_page(
            db,
            amo_id=seeded["amo_id"],
            page=1,
            page_size=25,
            filters=hr_schemas.HrPeopleFilterInput(pattern_state="DEFAULT"),
        )
        assert [item.user_id for item in default_pattern.items] == [seeded["alice"]]
    finally:
        _close_postgres_session(engine, connection, transaction, db)


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL integration database is not configured",
)
def test_people_facets_and_filtered_selection_are_tenant_scoped() -> None:
    engine, connection, transaction, db = _postgres_session()
    try:
        seeded = _seed_directory(db)
        facets = hr_people_directory.list_people_facets(db, amo_id=seeded["amo_id"])

        department_counts = {item.label: item.count for item in facets.departments}
        assert department_counts == {"Engineering": 2, "Quality": 2}
        group_counts = {item.label: item.count for item in facets.groups}
        assert group_counts == {"Engineering Duty Team": 2}
        assert {item.value: item.count for item in facets.contract_states} == {
            "EFFECTIVE": 2,
            "FUTURE": 1,
            "MISSING": 1,
        }

        selected = hr_people_directory.resolve_selection_user_ids(
            db,
            amo_id=seeded["amo_id"],
            selection=hr_schemas.HrPeopleSelection(
                mode="FILTERED",
                filters=hr_schemas.HrPeopleFilterInput(
                    group_id=seeded["engineering_group_id"],
                ),
                exclude_user_ids=[seeded["alice"]],
            ),
        )
        assert selected == [seeded["brian"]]
    finally:
        _close_postgres_session(engine, connection, transaction, db)


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL integration database is not configured",
)
def test_selected_default_pattern_batch_previews_applies_and_rejects_stale_counts() -> None:
    engine, connection, transaction, db = _postgres_session()
    try:
        seeded = _seed_directory(db)
        selection = hr_schemas.HrPeopleSelection(
            mode="FILTERED",
            filters=hr_schemas.HrPeopleFilterInput(
                group_id=seeded["engineering_group_id"],
            ),
            exclude_user_ids=[],
        )
        _, selection_token = hr_selection_integrity.resolve_with_token(
            db,
            amo_id=seeded["amo_id"],
            selection=selection,
        )

        preview = hr_people_directory.preview_default_day_pattern_batch(
            db,
            amo_id=seeded["amo_id"],
            selection=selection,
        )
        assert preview.matched_count == 2
        assert preview.eligible_count == 2
        assert preview.assignable_count == 1
        assert preview.already_assigned_count == 1
        assert len(selection_token) == 64

        changed_selection = hr_schemas.HrPeopleSelection(
            mode="FILTERED",
            filters=selection.filters,
            exclude_user_ids=[seeded["alice"]],
        )
        _, changed_token = hr_selection_integrity.resolve_with_token(
            db,
            amo_id=seeded["amo_id"],
            selection=changed_selection,
        )
        assert changed_token != selection_token

        with pytest.raises(ValueError, match="population changed"):
            hr_people_directory.apply_default_day_pattern_batch(
                db,
                amo_id=seeded["amo_id"],
                actor_user_id=seeded["alice"],
                payload=hr_schemas.HrDefaultDayBatchApplyRequest(
                    selection=selection,
                    expected_match_count=1,
                    expected_selection_token=selection_token,
                ),
            )

        result = hr_people_directory.apply_default_day_pattern_batch(
            db,
            amo_id=seeded["amo_id"],
            actor_user_id=seeded["alice"],
            payload=hr_schemas.HrDefaultDayBatchApplyRequest(
                selection=selection,
                expected_match_count=2,
                expected_selection_token=selection_token,
            ),
        )
        assert result.matched_count == 2
        assert result.assigned_count == 1
        assert result.already_assigned_count == 1
        assert db.query(models.EmployeeWorkPatternAssignment).filter(
            models.EmployeeWorkPatternAssignment.amo_id == seeded["amo_id"],
            models.EmployeeWorkPatternAssignment.user_id.in_([
                seeded["alice"],
                seeded["brian"],
            ]),
            models.EmployeeWorkPatternAssignment.effective_to.is_(None),
        ).count() == 2
    finally:
        _close_postgres_session(engine, connection, transaction, db)
