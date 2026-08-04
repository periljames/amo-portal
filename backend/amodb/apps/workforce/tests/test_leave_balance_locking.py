from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from amodb.apps.workforce import models, services
from amodb.apps.workforce.leave_balance_locking import (
    leave_balance_query,
    load_leave_balance_for_update,
)


def _leave_request_stub():
    return SimpleNamespace(
        amo_id="ID-AMO",
        user_id="ID-USER",
        leave_type_id="ID-LEAVE-TYPE",
        starts_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )


def test_leave_balance_lock_targets_only_the_balance_table_on_postgresql():
    with Session() as db:
        statement = leave_balance_query(
            db,
            request=_leave_request_stub(),
        ).with_for_update(of=models.EmployeeLeaveBalance).statement

    sql = str(statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )).upper()

    assert "LEFT OUTER JOIN" not in sql
    assert "FOR UPDATE OF EMPLOYEE_LEAVE_BALANCES" in sql


def test_all_leave_transitions_use_the_postgresql_safe_lock_helper():
    assert services._leave_balance is load_leave_balance_for_update
