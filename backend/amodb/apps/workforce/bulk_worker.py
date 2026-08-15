"""Bounded worker for durable Workforce bulk operations."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import lazyload

from ...database import WriteSessionLocal
from ..accounts import models as account_models
from ..audit import services as audit_services
from . import bulk_contracts, bulk_models, bulk_patterns, governance_mutations

logger = logging.getLogger(__name__)
PROCESS_CHUNK_SIZE = 100
TERMINAL_ITEM_STATUSES = ("SUCCEEDED", "SKIPPED", "FAILED")
TERMINAL_OPERATION_STATUSES = ("COMPLETED", "COMPLETED_WITH_ERRORS")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mark_item(
    item: bulk_models.WorkforceBulkOperationItem,
    *,
    status: str,
    code: str | None = None,
    message: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    item.status = status
    item.outcome_code = code
    item.outcome_message = message
    item.result_json = result
    item.completed_at = _utcnow()


def _refresh_counts(db, operation: bulk_models.WorkforceBulkOperation) -> None:
    query = db.query(bulk_models.WorkforceBulkOperationItem)
    filters = [bulk_models.WorkforceBulkOperationItem.operation_id == operation.id]
    operation.succeeded_count = query.filter(*filters, bulk_models.WorkforceBulkOperationItem.status == "SUCCEEDED").count()
    operation.skipped_count = query.filter(*filters, bulk_models.WorkforceBulkOperationItem.status == "SKIPPED").count()
    operation.failed_count = query.filter(*filters, bulk_models.WorkforceBulkOperationItem.status == "FAILED").count()
    operation.processed_count = operation.succeeded_count + operation.skipped_count + operation.failed_count


def process_operation(operation_id: str) -> None:
    """Run one operation in bounded commits; completed items are never repeated."""
    try:
        with WriteSessionLocal() as db:
            operation = db.query(bulk_models.WorkforceBulkOperation).filter(
                bulk_models.WorkforceBulkOperation.id == operation_id,
                bulk_models.WorkforceBulkOperation.status == "QUEUED",
            ).with_for_update(skip_locked=True).first()
            if operation is None or operation.status in TERMINAL_OPERATION_STATUSES:
                return
            operation.status = "RUNNING"
            operation.started_at = operation.started_at or _utcnow()
            operation.heartbeat_at = _utcnow()
            operation.last_error = None
            db.commit()

        while True:
            with WriteSessionLocal() as db:
                operation = db.query(bulk_models.WorkforceBulkOperation).filter(
                    bulk_models.WorkforceBulkOperation.id == operation_id,
                ).with_for_update().first()
                if operation is None:
                    return
                actor = db.query(account_models.User).filter(
                    account_models.User.id == operation.actor_user_id,
                    account_models.User.amo_id == operation.amo_id,
                    account_models.User.is_active.is_(True),
                ).first()
                if actor is None:
                    operation.status = "FAILED"
                    operation.last_error = "The initiating administrator is no longer active"
                    operation.completed_at = _utcnow()
                    db.commit()
                    return

                items = (
                    db.query(bulk_models.WorkforceBulkOperationItem)
                    # The item's operation relationship is joined by default.
                    # Suppress it for the claim so PostgreSQL is never asked to
                    # lock the nullable side of an outer join.
                    .options(lazyload(bulk_models.WorkforceBulkOperationItem.operation))
                    .filter(
                        bulk_models.WorkforceBulkOperationItem.operation_id == operation_id,
                        bulk_models.WorkforceBulkOperationItem.status == "PENDING",
                    )
                    .order_by(bulk_models.WorkforceBulkOperationItem.sequence.asc())
                    .limit(PROCESS_CHUNK_SIZE)
                    .with_for_update(
                        of=bulk_models.WorkforceBulkOperationItem,
                        skip_locked=True,
                    )
                    .all()
                )
                if not items:
                    _refresh_counts(db, operation)
                    operation.status = "COMPLETED_WITH_ERRORS" if operation.failed_count else "COMPLETED"
                    operation.completed_at = _utcnow()
                    operation.heartbeat_at = _utcnow()
                    audit_services.log_event(
                        db,
                        amo_id=operation.amo_id,
                        actor_user_id=operation.actor_user_id,
                        entity_type="WorkforceBulkOperation",
                        entity_id=str(operation.id),
                        action="complete",
                        correlation_id=str(operation.id),
                        after={
                            "status": operation.status,
                            "succeeded_count": operation.succeeded_count,
                            "skipped_count": operation.skipped_count,
                            "failed_count": operation.failed_count,
                        },
                        metadata={"module": "workforce"},
                    )
                    db.commit()
                    return

                for item in items:
                    item.status = "RUNNING"
                    item.started_at = _utcnow()
                    item.attempt_count += 1
                    item.outcome_code = "PROCESSING"
                    item.outcome_message = "Processing this personnel record"
                    operation.heartbeat_at = _utcnow()
                    # Publish the claimed item before doing the work.  The
                    # operation API can now report the current person instead
                    # of remaining at 0 until the whole chunk is finished.
                    db.commit()
                    try:
                        with db.begin_nested():
                            if operation.operation_type == "CREATE_CONTRACTS":
                                outcome = bulk_contracts.process_contract_item(
                                    db, operation=operation, item=item, actor=actor
                                )
                            elif operation.operation_type == "ASSIGN_DEFAULT_DAY_PATTERN":
                                outcome = bulk_contracts.process_default_pattern_item(
                                    db, operation=operation, item=item, actor=actor
                                )
                            elif operation.operation_type == "ASSIGN_WORK_PATTERN":
                                outcome = bulk_patterns.process_work_pattern_item(
                                    db, operation=operation, item=item, actor=actor
                                )
                            elif operation.operation_type in governance_mutations.MUTATION_TYPES:
                                outcome = governance_mutations.process_personnel_mutation_item(
                                    db, operation=operation, item=item, actor=actor
                                )
                            else:
                                raise ValueError(f"Unsupported bulk operation type: {operation.operation_type}")
                        _mark_item(
                            item,
                            status=outcome[0],
                            code=outcome[1],
                            message=outcome[2],
                            result=outcome[3],
                        )
                    except Exception as exc:
                        logger.exception(
                            "Workforce bulk item failed",
                            extra={"operation_id": operation_id, "user_id": item.user_id},
                        )
                        _mark_item(
                            item,
                            status="FAILED",
                            code="RECORD_PROCESSING_FAILED",
                            message=str(exc)[:2000],
                        )
                    db.add(item)
                    _refresh_counts(db, operation)
                    operation.heartbeat_at = _utcnow()
                    # Each completed record is its own durable progress
                    # checkpoint.  A crash can resume safely and the frontend
                    # receives steadily increasing counts and heartbeat data.
                    db.commit()
    except Exception as exc:
        logger.exception("Workforce bulk operation failed", extra={"operation_id": operation_id})
        with WriteSessionLocal() as db:
            operation = db.query(bulk_models.WorkforceBulkOperation).filter(
                bulk_models.WorkforceBulkOperation.id == operation_id,
            ).first()
            if operation is not None and operation.status not in TERMINAL_OPERATION_STATUSES:
                operation.status = "FAILED"
                operation.last_error = str(exc)[:4000]
                operation.completed_at = _utcnow()
                operation.heartbeat_at = _utcnow()
                db.commit()
