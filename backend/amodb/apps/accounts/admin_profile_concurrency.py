from __future__ import annotations

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_db


def _is_postgresql(db: Session) -> bool:
    bind = db.get_bind()
    return str(getattr(getattr(bind, "dialect", None), "name", "")) == "postgresql"


def lock_admin_grant_for_approval(
    grant_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Serialize approvers before the approval foreign-key insert occurs.

    Acquiring the parent-row lock as a route dependency means concurrent
    PostgreSQL requests cannot both take key-share locks for approval inserts and
    then deadlock while upgrading the grant row. SQLite test databases skip the
    unsupported lock clause.
    """
    if not _is_postgresql(db):
        return
    db.execute(
        text("SELECT id FROM admin_access_grants WHERE id = :grant_id FOR UPDATE"),
        {"grant_id": grant_id},
    ).first()


def serialized_approval_count(db: Session, grant_id: str) -> int:
    """Count committed approvals while the caller holds the grant-row lock."""
    value = db.execute(
        text(
            """
            SELECT COUNT(DISTINCT approver_user_id)
            FROM admin_access_grant_approvals
            WHERE grant_id = :grant_id AND decision = 'APPROVED'
            """
        ),
        {"grant_id": grant_id},
    ).scalar()
    return int(value or 0)
