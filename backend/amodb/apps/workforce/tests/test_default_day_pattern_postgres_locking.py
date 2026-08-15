from __future__ import annotations

import os
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.foundations import models as foundation_models
from amodb.apps.rostering import models as rostering_models  # noqa: F401
from amodb.apps.workforce import hr_service, models
from amodb.apps.workforce.work_pattern_assignment_locking import (
    scope_employee_pattern_for_update,
)


def _id() -> str:
    return str(uuid4())


def test_default_pattern_assignment_lock_targets_only_the_base_table() -> None:
    statement = select(models.EmployeeWorkPatternAssignment).with_for_update()
    before = str(statement.compile(dialect=postgresql.dialect()))

    assert "LEFT OUTER JOIN" in before
    assert before.rstrip().endswith("FOR UPDATE")

    state = SimpleNamespace(
        is_select=True,
        statement=statement,
        all_mappers=[models.EmployeeWorkPatternAssignment.__mapper__],
    )
    scope_employee_pattern_for_update(state)

    after = str(state.statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE OF employee_work_pattern_assignments" in after
    assert "FOR UPDATE OF users" not in after
    assert "FOR UPDATE OF work_patterns" not in after
    assert after.count("FOR UPDATE") == 1


def test_unlocked_assignment_query_is_not_modified() -> None:
    statement = select(models.EmployeeWorkPatternAssignment)
    state = SimpleNamespace(
        is_select=True,
        statement=statement,
        all_mappers=[models.EmployeeWorkPatternAssignment.__mapper__],
    )

    scope_employee_pattern_for_update(state)

    compiled = str(state.statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" not in compiled


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL integration database is not configured",
)
def test_default_day_bootstrap_creates_one_idempotent_assignment_on_postgresql() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, autoflush=False, expire_on_commit=False)

    today = date.today()
    amo_id = _id()
    user_id = _id()
    base_id = _id()

    try:
        db.add(
            account_models.AMO(
                id=amo_id,
                amo_code=f"BOOT-{amo_id[:8]}",
                name="Default Pattern PostgreSQL Test",
                login_slug=f"bootstrap-{amo_id[:8]}",
                time_zone="UTC",
            )
        )
        db.flush()

        db.add(
            foundation_models.BaseStation(
                id=base_id,
                amo_id=amo_id,
                code="BOOT-BASE",
                name="Bootstrap Base",
                base_type=foundation_models.BaseStationType.MAIN_BASE,
            )
        )
        db.flush()

        db.add(
            account_models.User(
                id=user_id,
                amo_id=amo_id,
                staff_code=f"BOOT-{user_id[:8]}",
                email=f"{user_id[:8]}@bootstrap-test.invalid",
                first_name="Bootstrap",
                last_name="Tester",
                full_name="Bootstrap Tester",
                role=account_models.AccountRole.PRODUCTION_ENGINEER,
                hashed_password="not-a-real-password-hash",
            )
        )
        db.flush()

        db.add(
            rostering_models.ShiftTemplate(
                id=_id(),
                amo_id=amo_id,
                code="D",
                label="Full Day",
                kind=rostering_models.ShiftTemplateKind.DAY,
                default_start_time="08:00",
                default_end_time="17:00",
                duration_minutes=480,
                counts_as_duty=True,
                is_active=True,
                display_order=10,
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
            )
        )
        db.flush()

        db.add(
            models.EmploymentContract(
                id=_id(),
                amo_id=amo_id,
                user_id=user_id,
                contract_type=models.ContractType.PERMANENT,
                employment_status=models.EmploymentStatus.ACTIVE,
                effective_from=today,
                effective_to=None,
                standard_weekly_minutes=2400,
                standard_daily_minutes=480,
                fte_percentage=100,
                primary_base_station_id=base_id,
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
            )
        )
        db.flush()

        first = hr_service.bootstrap_default_day_pattern(
            db,
            amo_id=amo_id,
            actor_user_id=user_id,
        )

        assert first.eligible_user_count == 1
        assert first.assigned_user_count == 1
        assert first.already_assigned_count == 0

        assignment = (
            db.query(models.EmployeeWorkPatternAssignment)
            .filter(
                models.EmployeeWorkPatternAssignment.amo_id == amo_id,
                models.EmployeeWorkPatternAssignment.user_id == user_id,
            )
            .one()
        )
        assert str(assignment.work_pattern_id) == str(first.work_pattern_id)
        assert assignment.effective_from == today
        assert assignment.cycle_anchor_date.weekday() == 0

        second = hr_service.bootstrap_default_day_pattern(
            db,
            amo_id=amo_id,
            actor_user_id=user_id,
        )

        assert second.eligible_user_count == 1
        assert second.assigned_user_count == 0
        assert second.already_assigned_count == 1
        assert (
            db.query(models.EmployeeWorkPatternAssignment)
            .filter(
                models.EmployeeWorkPatternAssignment.amo_id == amo_id,
                models.EmployeeWorkPatternAssignment.user_id == user_id,
            )
            .count()
            == 1
        )
    finally:
        db.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()
