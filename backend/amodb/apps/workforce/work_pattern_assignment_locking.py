"""PostgreSQL-safe row locking for Workforce models with joined loaders.

Several Workforce models load related users and templates with LEFT OUTER JOINs.
PostgreSQL rejects an unqualified ``FOR UPDATE`` for those statements because
rows on the nullable side of an outer join cannot be locked. Scope each lock to
its authoritative base table without weakening the transaction lock itself.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
from typing import Iterator

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session

from . import models

_INSTALLED_FLAG = "_postgres_safe_workforce_locks_installed"


def _scope_model_for_update(execute_state: ORMExecuteState, model_type) -> None:
    if not execute_state.is_select:
        return

    statement = execute_state.statement
    lock = getattr(statement, "_for_update_arg", None)
    if lock is None:
        return
    if model_type.__mapper__ not in execute_state.all_mappers:
        return

    execute_state.statement = statement.with_for_update(
        nowait=bool(lock.nowait),
        read=bool(lock.read),
        of=model_type,
        skip_locked=bool(lock.skip_locked),
        key_share=bool(lock.key_share),
    )


def scope_employee_pattern_for_update(execute_state: ORMExecuteState) -> None:
    """Restrict assignment ``FOR UPDATE`` statements to their base table."""
    _scope_model_for_update(execute_state, models.EmployeeWorkPatternAssignment)


def scope_overtime_request_for_update(execute_state: ORMExecuteState) -> None:
    """Restrict overtime-request locks to the request table."""
    _scope_model_for_update(execute_state, models.OvertimeRequest)


@contextmanager
def _postgres_safe_lock_scope(db: Session, listener) -> Iterator[None]:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return

    event.listen(db, "do_orm_execute", listener)
    try:
        yield
    finally:
        event.remove(db, "do_orm_execute", listener)


@contextmanager
def postgres_safe_assignment_lock_scope(db: Session) -> Iterator[None]:
    """Apply PostgreSQL-safe assignment locks for one service operation."""
    with _postgres_safe_lock_scope(db, scope_employee_pattern_for_update):
        yield


@contextmanager
def postgres_safe_overtime_lock_scope(db: Session) -> Iterator[None]:
    """Apply PostgreSQL-safe overtime locks for one service operation."""
    with _postgres_safe_lock_scope(db, scope_overtime_request_for_update):
        yield


def install_default_day_pattern_lock_scope(hr_service_module) -> None:
    """Wrap affected HR operations once so every call path receives safe locks."""
    if getattr(hr_service_module, _INSTALLED_FLAG, False):
        return

    original_bootstrap = hr_service_module.bootstrap_default_day_pattern
    original_decide_overtime = hr_service_module.decide_overtime

    @wraps(original_bootstrap)
    def wrapped_bootstrap(db: Session, *args, **kwargs):
        with postgres_safe_assignment_lock_scope(db):
            return original_bootstrap(db, *args, **kwargs)

    @wraps(original_decide_overtime)
    def wrapped_decide_overtime(db: Session, *args, **kwargs):
        with postgres_safe_overtime_lock_scope(db):
            return original_decide_overtime(db, *args, **kwargs)

    hr_service_module.bootstrap_default_day_pattern = wrapped_bootstrap
    hr_service_module.decide_overtime = wrapped_decide_overtime
    setattr(hr_service_module, _INSTALLED_FLAG, True)
