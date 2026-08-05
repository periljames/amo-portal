"""PostgreSQL-safe row locking for employee work-pattern assignments.

EmployeeWorkPatternAssignment uses joined relationship loading for its employee
and work-pattern references. PostgreSQL rejects a generic ``FOR UPDATE`` when
those relationships produce LEFT OUTER JOINs because the nullable side of an
outer join cannot be locked. Scope the lock to the assignment table while the
idempotent default-pattern bootstrap runs.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
from typing import Iterator

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session

from . import models

_INSTALLED_FLAG = "_postgres_safe_default_pattern_locks_installed"


def scope_employee_pattern_for_update(execute_state: ORMExecuteState) -> None:
    """Restrict assignment ``FOR UPDATE`` statements to their base table."""
    if not execute_state.is_select:
        return

    statement = execute_state.statement
    lock = getattr(statement, "_for_update_arg", None)
    if lock is None:
        return
    if models.EmployeeWorkPatternAssignment.__mapper__ not in execute_state.all_mappers:
        return

    execute_state.statement = statement.with_for_update(
        nowait=bool(lock.nowait),
        read=bool(lock.read),
        of=models.EmployeeWorkPatternAssignment,
        skip_locked=bool(lock.skip_locked),
        key_share=bool(lock.key_share),
    )


@contextmanager
def postgres_safe_assignment_lock_scope(db: Session) -> Iterator[None]:
    """Apply PostgreSQL-safe assignment locks for one service operation."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return

    event.listen(db, "do_orm_execute", scope_employee_pattern_for_update)
    try:
        yield
    finally:
        event.remove(db, "do_orm_execute", scope_employee_pattern_for_update)


def install_default_day_pattern_lock_scope(hr_service_module) -> None:
    """Wrap the bootstrap once so every call path receives the lock fix."""
    if getattr(hr_service_module, _INSTALLED_FLAG, False):
        return

    original = hr_service_module.bootstrap_default_day_pattern

    @wraps(original)
    def wrapped(db: Session, *args, **kwargs):
        with postgres_safe_assignment_lock_scope(db):
            return original(db, *args, **kwargs)

    hr_service_module.bootstrap_default_day_pattern = wrapped
    setattr(hr_service_module, _INSTALLED_FLAG, True)
