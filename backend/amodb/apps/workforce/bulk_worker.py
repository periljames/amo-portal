"""Bounded worker for durable Workforce bulk operations."""
from __future__ import annotations

import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import lazyload

from ...database import WriteSessionLocal
from ..accounts import models as account_models
from ..audit import services as audit_services
from . import bulk_contracts, bulk_models, bulk_patterns, governance_mutations

logger = logging.getLogger(__name__)
PROCESS_CHUNK_SIZE = max(50, min(int(os.getenv("WORKFORCE_BULK_CHUNK_SIZE", "500")), 2_000))
CLAIM_LEASE_SECONDS = max(30, min(int(os.getenv("WORKFORCE_BULK_CLAIM_LEASE_SECONDS", "300")), 3_600))
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
    counts = dict(
        db.query(
            bulk_models.WorkforceBulkOperationItem.status,
            func.count(bulk_models.WorkforceBulkOperationItem.id),
        ).filter(
            bulk_models.WorkforceBulkOperationItem.operation_id == operation.id,
        ).group_by(
            bulk_models.WorkforceBulkOperationItem.status,
        ).all()
    )
    operation.succeeded_count = int(counts.get("SUCCEEDED", 0))
    operation.skipped_count = int(counts.get("SKIPPED", 0))
    operation.failed_count = int(counts.get("FAILED", 0))
    operation.processed_count = operation.succeeded_count + operation.skipped_count + operation.failed_count


def _claim_chunk(operation_id: str, *, worker_id: str) -> str | None:
    """Atomically lease a small group of items and release DB locks immediately."""
    now = _utcnow()
    token = uuid.uuid4().hex
    with WriteSessionLocal() as db:
        operation_query = db.query(bulk_models.WorkforceBulkOperation).options(
            lazyload(bulk_models.WorkforceBulkOperation.items),
        ).filter(
            bulk_models.WorkforceBulkOperation.id == operation_id,
            bulk_models.WorkforceBulkOperation.status.in_(("QUEUED", "RUNNING")),
        )
        if db.get_bind().dialect.name == "postgresql":
            operation_query = operation_query.with_for_update(skip_locked=True)
        operation = operation_query.first()
        if operation is None:
            return None
        operation.status = "RUNNING"
        operation.started_at = operation.started_at or now
        operation.heartbeat_at = now
        operation.last_error = None

        items_query = (
            db.query(bulk_models.WorkforceBulkOperationItem)
            .options(lazyload(bulk_models.WorkforceBulkOperationItem.operation))
            .filter(
                bulk_models.WorkforceBulkOperationItem.operation_id == operation_id,
                or_(
                    bulk_models.WorkforceBulkOperationItem.status == "PENDING",
                    (
                        (bulk_models.WorkforceBulkOperationItem.status == "RUNNING")
                        & (bulk_models.WorkforceBulkOperationItem.claim_expires_at < now)
                    ),
                ),
            )
            .order_by(bulk_models.WorkforceBulkOperationItem.sequence.asc())
            .limit(PROCESS_CHUNK_SIZE)
        )
        if db.get_bind().dialect.name == "postgresql":
            items_query = items_query.with_for_update(
                of=bulk_models.WorkforceBulkOperationItem, skip_locked=True
            )
        else:
            items_query = items_query.with_for_update()
        items = items_query.all()
        if not items:
            _refresh_counts(db, operation)
            active = db.query(func.count(bulk_models.WorkforceBulkOperationItem.id)).filter(
                bulk_models.WorkforceBulkOperationItem.operation_id == operation_id,
                bulk_models.WorkforceBulkOperationItem.status.in_(("PENDING", "RUNNING")),
            ).scalar() or 0
            if active == 0:
                operation.status = "COMPLETED_WITH_ERRORS" if operation.failed_count else "COMPLETED"
                operation.completed_at = now
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
                    metadata={"module": "workforce", "claim_mode": "item-level"},
                )
            db.commit()
            return None
        for item in items:
            item.status = "RUNNING"
            item.started_at = item.started_at or now
            item.attempt_count += 1
            item.claim_token = token
            item.claimed_by = worker_id[:128]
            item.claim_expires_at = now + timedelta(seconds=CLAIM_LEASE_SECONDS)
            item.outcome_code = "PROCESSING"
            item.outcome_message = "Processing this personnel record"
        db.commit()
        return token


def _process_claim(operation_id: str, claim_token: str) -> int:
    with WriteSessionLocal() as db:
        operation = db.query(bulk_models.WorkforceBulkOperation).options(
            lazyload(bulk_models.WorkforceBulkOperation.items),
        ).filter(
            bulk_models.WorkforceBulkOperation.id == operation_id,
        ).first()
        if operation is None:
            return 0
        actor = db.query(account_models.User).filter(
            account_models.User.id == operation.actor_user_id,
            account_models.User.amo_id == operation.amo_id,
            account_models.User.is_active.is_(True),
        ).first()
        items = (
            db.query(bulk_models.WorkforceBulkOperationItem)
            .options(lazyload(bulk_models.WorkforceBulkOperationItem.operation))
            .filter(
                bulk_models.WorkforceBulkOperationItem.operation_id == operation_id,
                bulk_models.WorkforceBulkOperationItem.claim_token == claim_token,
                bulk_models.WorkforceBulkOperationItem.status == "RUNNING",
            )
            .order_by(bulk_models.WorkforceBulkOperationItem.sequence.asc())
            .all()
        )
        if not items:
            return 0
        if actor is None:
            for item in items:
                _mark_item(item, status="FAILED", code="ACTOR_INACTIVE", message="The initiating administrator is no longer active")
        elif operation.operation_type == "ASSIGN_WORK_PATTERN":
            try:
                with db.begin_nested():
                    outcomes = bulk_patterns.process_work_pattern_items(db, operation=operation, items=items, actor=actor)
                for item in items:
                    outcome = outcomes.get(str(item.id)) or (
                        "FAILED", "RECORD_PROCESSING_FAILED", "The batch processor did not return an outcome", None,
                    )
                    _mark_item(item, status=outcome[0], code=outcome[1], message=outcome[2], result=outcome[3])
            except Exception as exc:
                logger.exception("Workforce work-pattern claim failed", extra={"operation_id": operation_id, "item_count": len(items)})
                for item in items:
                    _mark_item(item, status="FAILED", code="CHUNK_PROCESSING_FAILED", message=str(exc)[:2000])
        else:
            for item in items:
                try:
                    with db.begin_nested():
                        if operation.operation_type == "CREATE_CONTRACTS":
                            outcome = bulk_contracts.process_contract_item(db, operation=operation, item=item, actor=actor)
                        elif operation.operation_type == "ASSIGN_DEFAULT_DAY_PATTERN":
                            outcome = bulk_contracts.process_default_pattern_item(db, operation=operation, item=item, actor=actor)
                        elif operation.operation_type in governance_mutations.MUTATION_TYPES:
                            outcome = governance_mutations.process_personnel_mutation_item(db, operation=operation, item=item, actor=actor)
                        else:
                            raise ValueError(f"Unsupported bulk operation type: {operation.operation_type}")
                    _mark_item(item, status=outcome[0], code=outcome[1], message=outcome[2], result=outcome[3])
                except Exception as exc:
                    logger.exception("Workforce bulk item failed", extra={"operation_id": operation_id, "user_id": item.user_id})
                    _mark_item(item, status="FAILED", code="RECORD_PROCESSING_FAILED", message=str(exc)[:2000])
        for item in items:
            item.claim_token = None
            item.claim_expires_at = None
            item.claimed_by = None
        _refresh_counts(db, operation)
        operation.heartbeat_at = _utcnow()
        db.commit()
        return len(items)


def process_operation(operation_id: str, *, max_chunks: int | None = None, worker_id: str | None = None) -> int:
    """Process leased chunks. Different processes may safely share one operation."""
    identity = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    processed = 0
    chunks = 0
    try:
        while True:
            token = _claim_chunk(operation_id, worker_id=identity)
            if token is None:
                return processed
            processed += _process_claim(operation_id, token)
            chunks += 1
            if max_chunks is not None and chunks >= max_chunks:
                return processed
    except Exception as exc:
        logger.exception("Workforce bulk operation failed", extra={"operation_id": operation_id})
        with WriteSessionLocal() as db:
            operation = db.query(bulk_models.WorkforceBulkOperation).options(
                lazyload(bulk_models.WorkforceBulkOperation.items),
            ).filter(
                bulk_models.WorkforceBulkOperation.id == operation_id,
            ).first()
            if operation is not None and operation.status not in TERMINAL_OPERATION_STATUSES:
                operation.last_error = str(exc)[:4000]
                operation.heartbeat_at = _utcnow()
                db.commit()
        return processed
