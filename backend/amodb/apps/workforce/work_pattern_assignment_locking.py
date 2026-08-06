"""PostgreSQL-safe row locking for employee work-pattern assignments.

``EmployeeWorkPatternAssignment`` eagerly loads its employee and work-pattern
relationships. PostgreSQL rejects a generic ``FOR UPDATE`` when those joined
relationships produce nullable outer-join rows. The default-day bootstrap only
needs to serialize changes to the assignment records, so scope the lock to that
base table.
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
    """Wrap the default-day bootstrap once for every application call path."""
    if getattr(hr_service_module, _INSTALLED_FLAG, False):
        return

    original = hr_service_module.bootstrap_default_day_pattern

    @wraps(original)
    def wrapped(db: Session, *args, **kwargs):
        with postgres_safe_assignment_lock_scope(db):
            return original(db, *args, **kwargs)

    hr_service_module.bootstrap_default_day_pattern = wrapped
    setattr(hr_service_module, _INSTALLED_FLAG, True)
