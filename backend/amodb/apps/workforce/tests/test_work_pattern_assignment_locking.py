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
from amodb.apps.workforce import hr_service, models
from amodb.apps.workforce.work_pattern_assignment_locking import (
    postgres_safe_assignment_lock_scope,
    scope_employee_pattern_for_update,
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


def test_assignment_lock_is_scoped_to_the_base_table() -> None:
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
    assert after.count("FOR UPDATE") == 1


def test_unlocked_assignment_query_is_not_changed() -> None:
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
def test_scoped_assignment_lock_executes_on_postgresql() -> None:
    engine, connection, transaction, db = _postgres_session()

    amo_id = _id()
    user_id = _id()
    pattern_id = _id()
    assignment_id = _id()

    try:
        db.add(
            account_models.AMO(
                id=amo_id,
                amo_code=f"LOCK-{amo_id[:8]}",
                name="Work Pattern Lock Test",
                login_slug=f"lock-{amo_id[:8]}",
            )
        )
        db.flush()

        db.add(
            account_models.User(
                id=user_id,
                amo_id=amo_id,
                staff_code=f"LOCK-{user_id[:8]}",
                email=f"{user_id[:8]}@lock-test.invalid",
                first_name="Lock",
                last_name="Tester",
                full_name="Lock Tester",
                role=account_models.AccountRole.TECHNICIAN,
                hashed_password="not-a-real-password-hash",
            )
        )
        db.flush()

        db.add(
            models.WorkPattern(
                id=pattern_id,
                amo_id=amo_id,
                code=f"LOCK-{pattern_id[:8]}",
                name="Lock Test Pattern",
                cycle_length_days=7,
                is_active=True,
                timezone_name="UTC",
            )
        )
        db.flush()

        db.add(
            models.EmployeeWorkPatternAssignment(
                id=assignment_id,
                amo_id=amo_id,
                user_id=user_id,
                work_pattern_id=pattern_id,
                effective_from=date(2026, 8, 5),
                effective_to=None,
                cycle_anchor_date=date(2026, 8, 3),
            )
        )
        db.flush()

        with postgres_safe_assignment_lock_scope(db):
            row = (
                db.query(models.EmployeeWorkPatternAssignment)
                .filter(models.EmployeeWorkPatternAssignment.id == assignment_id)
                .with_for_update()
                .first()
            )

        assert row is not None
        assert str(row.id) == assignment_id
    finally:
        _close_postgres_session(engine, connection, transaction, db)


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL integration database is not configured",
)
def test_default_day_bootstrap_assigns_contracted_user_on_postgresql() -> None:
    engine, connection, transaction, db = _postgres_session()

    today = date.today()
    amo_id = _id()
    user_id = _id()
    base_id = _id()

    try:
        db.add(
            account_models.AMO(
                id=amo_id,
                amo_code=f"BOOT-{amo_id[:8]}",
                name="Default Pattern Bootstrap Test",
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
                role=account_models.AccountRole.TECHNICIAN,
                hashed_password="not-a-real-password-hash",
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
        _close_postgres_session(engine, connection, transaction, db)
