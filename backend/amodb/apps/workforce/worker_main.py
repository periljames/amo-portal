"""Standalone process for durable Workforce bulk operations and offboarding."""
from __future__ import annotations

import argparse
import logging
import os
import time

from ...database import WriteSessionLocal
from ..rostering import models as _rostering_models  # noqa: F401
from . import bulk_models, governance_mutations
from .bulk_worker import process_operation


def run_once(*, operation_limit: int = 10) -> int:
    # Workforce work-pattern models reference Rostering's ShiftTemplate by
    # SQLAlchemy class name. The web application imports both domains before
    # mapper configuration; the standalone worker must register the Rostering
    # models explicitly so its first database query has the same mapper graph.
    with WriteSessionLocal() as db:
        completed_offboarding = governance_mutations.apply_due_offboarding(db, limit=100)
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
    return len(operation_ids) + completed_offboarding


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
