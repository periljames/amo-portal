"""Standalone process for durable Workforce bulk operations and offboarding."""
from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from ...database import WriteSessionLocal
from ..rostering import models as _rostering_models  # noqa: F401
from . import bulk_models, governance_mutations, services
from .bulk_worker import process_operation


def _recover_stale_operations(db) -> int:
    stale_seconds = max(300, min(int(os.getenv("WORKFORCE_BULK_STALE_SECONDS", "900")), 86_400))
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)
    query = (
        db.query(bulk_models.WorkforceBulkOperation)
        .filter(
            bulk_models.WorkforceBulkOperation.status == "RUNNING",
            or_(
                bulk_models.WorkforceBulkOperation.heartbeat_at < cutoff,
                (
                    bulk_models.WorkforceBulkOperation.heartbeat_at.is_(None)
                    & (bulk_models.WorkforceBulkOperation.started_at < cutoff)
                ),
            ),
        )
        .order_by(bulk_models.WorkforceBulkOperation.heartbeat_at.asc())
        .limit(20)
    )
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    else:
        query = query.with_for_update()
    rows = query.all()
    for operation in rows:
        db.query(bulk_models.WorkforceBulkOperationItem).filter(
            bulk_models.WorkforceBulkOperationItem.operation_id == operation.id,
            bulk_models.WorkforceBulkOperationItem.status == "RUNNING",
        ).update(
            {
                bulk_models.WorkforceBulkOperationItem.status: "PENDING",
                bulk_models.WorkforceBulkOperationItem.outcome_code: "AUTOMATICALLY_RECOVERED",
                bulk_models.WorkforceBulkOperationItem.outcome_message: (
                    "The interrupted record was returned to the durable processing queue"
                ),
                bulk_models.WorkforceBulkOperationItem.completed_at: None,
            },
            synchronize_session=False,
        )
        operation.status = "QUEUED"
        operation.last_error = "Automatically resumed after the worker heartbeat expired"
        operation.completed_at = None
        operation.heartbeat_at = datetime.now(timezone.utc)
        db.add(operation)
    return len(rows)


def run_once(*, operation_limit: int = 10) -> int:
    # Workforce work-pattern models reference Rostering's ShiftTemplate by
    # SQLAlchemy class name. The web application imports both domains before
    # mapper configuration; the standalone worker must register the Rostering
    # models explicitly so its first database query has the same mapper graph.
    with WriteSessionLocal() as db:
        completed_offboarding = governance_mutations.apply_due_offboarding(db, limit=100)
        recovered_operations = _recover_stale_operations(db)
        attendance_result = services.reconcile_open_attendance_sessions(db, limit=200)
        db.commit()
        operation_ids = [
            str(operation_id)
            for (operation_id,) in db.query(bulk_models.WorkforceBulkOperation.id).filter(
                bulk_models.WorkforceBulkOperation.status == "QUEUED"
            ).order_by(
                bulk_models.WorkforceBulkOperation.created_at.asc(),
                bulk_models.WorkforceBulkOperation.id.asc(),
            ).limit(max(1, min(operation_limit, 100))).all()
        ]
    for operation_id in operation_ids:
        process_operation(operation_id)
    return (
        len(operation_ids)
        + completed_offboarding
        + recovered_operations
        + attendance_result["reminded"]
        + attendance_result["closed"]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Workforce durable-operation worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("WORKFORCE_WORKER_POLL_SECONDS", "2")))
    parser.add_argument("--operation-limit", type=int, default=int(os.getenv("WORKFORCE_WORKER_OPERATION_LIMIT", "10")))
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    while True:
        processed = run_once(operation_limit=args.operation_limit)
        if args.once:
            return
        if processed == 0:
            time.sleep(max(0.5, args.poll_seconds))


if __name__ == "__main__":
    main()
