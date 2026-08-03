from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def serialized_approval_count(db: Session, grant_id: str) -> int:
    """Count approvals after serialising writers on the grant row.

    PostgreSQL's default READ COMMITTED isolation allows two independent
    approvers to insert concurrently. Locking the parent grant before counting
    guarantees that the second transaction observes the first committed
    approval and can activate the grant without requiring a third approver.
    SQLite test databases do not support FOR UPDATE, so they use the same count
    without the lock clause.
    """
    bind = db.get_bind()
    dialect_name = str(getattr(getattr(bind, "dialect", None), "name", ""))
    if dialect_name == "postgresql":
        db.execute(
            text("SELECT id FROM admin_access_grants WHERE id = :grant_id FOR UPDATE"),
            {"grant_id": grant_id},
        ).first()

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
