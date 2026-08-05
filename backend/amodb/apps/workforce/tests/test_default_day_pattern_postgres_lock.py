from __future__ import annotations

import inspect

from sqlalchemy import column, select, table
from sqlalchemy.dialects import postgresql

from amodb.apps.workforce import hr_service


def test_default_day_bootstrap_scopes_the_lock_to_assignment_rows():
    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)

    assert ".with_for_update(of=models.EmployeeWorkPatternAssignment).all()" in source
    assert ".with_for_update().all()" not in source


def test_postgres_for_update_of_allows_the_eager_load_outer_join():
    assignments = table(
        "employee_work_pattern_assignments",
        column("id"),
        column("work_pattern_id"),
    )
    patterns = table("work_patterns", column("id"))
    statement = (
        select(assignments.c.id)
        .select_from(
            assignments.outerjoin(
                patterns,
                patterns.c.id == assignments.c.work_pattern_id,
            )
        )
        .with_for_update(of=assignments)
    )

    sql = " ".join(
        str(statement.compile(dialect=postgresql.dialect())).split()
    )

    assert "LEFT OUTER JOIN work_patterns" in sql
    assert "FOR UPDATE OF employee_work_pattern_assignments" in sql
