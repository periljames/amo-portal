"""Retention worker for Quality audit recycle-bin records.

Operational delete actions only add a tombstone. This worker is the sole
automatic purge path and removes records after the governed 30-day recovery
window. Manual permanent deletion remains available from the recycle bin.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from amodb.apps.quality import models
from amodb.apps.quality.audit_deletion_service import (
    AuditDeletionError,
    RECYCLE_BIN_RETENTION_DAYS,
    permanently_delete_audit,
)
from amodb.database import WriteSessionLocal, close_session_safely


logger = logging.getLogger(__name__)


def run_once(*, now: datetime | None = None, limit: int = 1000) -> dict[str, int]:
    """Purge one bounded batch of expired audits and schedules."""

    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    cutoff = clock - timedelta(days=RECYCLE_BIN_RETENTION_DAYS)
    batch_limit = max(1, min(int(limit), 5000))
    summary = {"audits_purged": 0, "schedules_purged": 0, "failed": 0}
    db = WriteSessionLocal()
    try:
        # Schedules do not own uploaded audit evidence and can be removed as a
        # compact batch. Programme links follow their declared FK behaviour.
        schedules = (
            db.query(models.QMSAuditSchedule)
            .filter(
                models.QMSAuditSchedule.deleted_at.is_not(None),
                models.QMSAuditSchedule.deleted_at <= cutoff,
            )
            .order_by(models.QMSAuditSchedule.deleted_at.asc())
            .limit(batch_limit)
            .all()
        )
        for schedule in schedules:
            db.delete(schedule)
        if schedules:
            db.commit()
            summary["schedules_purged"] = len(schedules)

        audits = (
            db.query(models.QMSAudit)
            .filter(
                models.QMSAudit.deleted_at.is_not(None),
                models.QMSAudit.deleted_at <= cutoff,
            )
            .order_by(models.QMSAudit.deleted_at.asc())
            .limit(batch_limit)
            .all()
        )
        for audit in audits:
            audit_id = str(audit.id)
            try:
                permanently_delete_audit(
                    db,
                    audit=audit,
                    actor_user_id="quality-recycle-bin-retention",
                )
                summary["audits_purged"] += 1
            except AuditDeletionError:
                summary["failed"] += 1
                logger.exception("Expired Quality audit purge failed", extra={"audit_id": audit_id})
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        close_session_safely(db)
