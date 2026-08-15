"""Durable, idempotent and retryable Workforce bulk-operation service."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..audit import services as audit_services
from . import bulk_contracts, bulk_models, bulk_patterns, bulk_schemas, hr_selection_integrity, legacy_guard
from .bulk_worker import process_operation

MAX_BULK_RECORDS = 10_000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_hash(value: dict[str, Any]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _operation_read(row: bulk_models.WorkforceBulkOperation) -> bulk_schemas.BulkOperationRead:
    progress = 100.0 if row.total_count == 0 else round((row.processed_count / row.total_count) * 100, 1)
    return bulk_schemas.BulkOperationRead(
        id=str(row.id), operation_type=row.operation_type, status=row.status,
        idempotency_key=row.idempotency_key, selection_token=row.selection_token,
        total_count=row.total_count, processed_count=row.processed_count,
        succeeded_count=row.succeeded_count, skipped_count=row.skipped_count,
        failed_count=row.failed_count, progress_percent=min(progress, 100.0),
        retry_of_operation_id=row.retry_of_operation_id, last_error=row.last_error,
        started_at=row.started_at, completed_at=row.completed_at,
        heartbeat_at=row.heartbeat_at, created_at=row.created_at, updated_at=row.updated_at,
    )


def get_operation(db: Session, *, amo_id: str, operation_id: str):
    return db.query(bulk_models.WorkforceBulkOperation).filter(
        bulk_models.WorkforceBulkOperation.amo_id == amo_id,
        bulk_models.WorkforceBulkOperation.id == operation_id,
    ).first()


def read_operation(db: Session, *, amo_id: str, operation_id: str):
    row = get_operation(db, amo_id=amo_id, operation_id=operation_id)
    if row is None:
        raise ValueError("Bulk operation not found")
    return _operation_read(row)


def preview_contract_batch(db: Session, *, amo_id: str, actor, payload):
    return bulk_contracts.preview_contract_batch(db, amo_id=amo_id, actor=actor, payload=payload)


def preview_work_pattern_batch(db: Session, *, amo_id: str, actor, payload):
    return bulk_patterns.preview_work_pattern_batch(db, amo_id=amo_id, actor=actor, payload=payload)


def _create_operation(
    db: Session, *, amo_id: str, actor_user_id: str, operation_type: str,
    idempotency_key: str, selection_token: str, user_ids: list[str],
    selection_snapshot: dict[str, Any], payload_json: dict[str, Any],
    item_inputs: dict[str, dict[str, Any]] | None = None,
    retry_of_operation_id: str | None = None,
):
    request_hash = _canonical_hash({
        "operation_type": operation_type, "selection_token": selection_token,
        "user_ids": user_ids, "payload": payload_json,
        "retry_of_operation_id": retry_of_operation_id,
    })
    existing = db.query(bulk_models.WorkforceBulkOperation).filter(
        bulk_models.WorkforceBulkOperation.amo_id == amo_id,
        bulk_models.WorkforceBulkOperation.actor_user_id == actor_user_id,
        bulk_models.WorkforceBulkOperation.operation_type == operation_type,
        bulk_models.WorkforceBulkOperation.idempotency_key == idempotency_key,
    ).first()
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("The idempotency key was already used for a different bulk request")
        return existing, False

    row = bulk_models.WorkforceBulkOperation(
        amo_id=amo_id, actor_user_id=actor_user_id, operation_type=operation_type,
        status="QUEUED", idempotency_key=idempotency_key, request_hash=request_hash,
        selection_token=selection_token, selection_snapshot=selection_snapshot,
        payload_json=payload_json, retry_of_operation_id=retry_of_operation_id,
        total_count=len(user_ids),
    )
    db.add(row)
    db.flush()
    for sequence, user_id in enumerate(user_ids):
        db.add(bulk_models.WorkforceBulkOperationItem(
            operation_id=row.id, amo_id=amo_id, user_id=user_id, sequence=sequence,
            status="PENDING", input_json=(item_inputs or {}).get(user_id),
        ))
    db.flush()
    audit_services.log_event(
        db, amo_id=amo_id, actor_user_id=actor_user_id,
        entity_type="WorkforceBulkOperation", entity_id=str(row.id), action="create",
        correlation_id=str(row.id),
        after={"operation_type": operation_type, "total_count": len(user_ids),
               "selection_token": selection_token, "retry_of_operation_id": retry_of_operation_id},
        metadata={"module": "workforce", "idempotency_key": idempotency_key},
    )
    return row, True


def _resolve_checked_selection(db, *, amo_id: str, payload):
    user_ids, selection_token = hr_selection_integrity.resolve_with_token(
        db, amo_id=amo_id, selection=payload.selection
    )
    if len(user_ids) != payload.expected_match_count or selection_token != payload.expected_selection_token:
        raise ValueError("The selected population changed after preview; review it again before submission")
    if not user_ids:
        raise ValueError("At least one person must be selected")
    if len(user_ids) > MAX_BULK_RECORDS:
        raise ValueError(f"Bulk operations are limited to {MAX_BULK_RECORDS:,} records")
    return user_ids, selection_token


def submit_contract_batch(db: Session, *, amo_id: str, actor, idempotency_key: str, payload):
    user_ids, selection_token = _resolve_checked_selection(db, amo_id=amo_id, payload=payload)
    override_by_user = {row.user_id: row for row in payload.overrides}
    if set(override_by_user) - set(user_ids):
        raise ValueError("Contract overrides may only reference selected users")
    item_inputs = {
        user_id: bulk_contracts.contract_input_for(
            payload.defaults, override_by_user.get(user_id), user_id=user_id
        ) for user_id in user_ids
    }
    row, created = _create_operation(
        db, amo_id=amo_id, actor_user_id=str(actor.id), operation_type="CREATE_CONTRACTS",
        idempotency_key=idempotency_key, selection_token=selection_token, user_ids=user_ids,
        selection_snapshot=payload.selection.model_dump(mode="json"),
        payload_json={"defaults": payload.defaults.model_dump(mode="json"),
                      "overrides": [item.model_dump(mode="json") for item in payload.overrides]},
        item_inputs=item_inputs,
    )
    return _operation_read(row), created


def submit_default_pattern_batch(db: Session, *, amo_id: str, actor, idempotency_key: str, payload):
    raise ValueError(legacy_guard.RETIRED_DEFAULT_PATTERN_MESSAGE)


def submit_work_pattern_batch(db: Session, *, amo_id: str, actor, idempotency_key: str, payload):
    user_ids, selection_token = _resolve_checked_selection(db, amo_id=amo_id, payload=payload)
    _pattern, candidates = bulk_patterns.classify_work_pattern_batch(
        db,
        amo_id=amo_id,
        actor=actor,
        user_ids=user_ids,
        options=payload.options,
    )
    actionable_user_ids = [row.user_id for row in candidates if row.eligible]
    if not actionable_user_ids:
        raise ValueError("No selected personnel require an eligible work-pattern change")
    item_payload = payload.options.model_dump(mode="json")
    row, created = _create_operation(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        operation_type="ASSIGN_WORK_PATTERN",
        idempotency_key=idempotency_key,
        selection_token=selection_token,
        user_ids=actionable_user_ids,
        selection_snapshot=payload.selection.model_dump(mode="json"),
        payload_json={**item_payload, "matched_count": len(user_ids)},
        item_inputs={user_id: item_payload for user_id in actionable_user_ids},
    )
    return _operation_read(row), created


def list_operations(db: Session, *, amo_id: str, page: int, page_size: int, status=None, operation_type=None):
    query = db.query(bulk_models.WorkforceBulkOperation).filter(
        bulk_models.WorkforceBulkOperation.amo_id == amo_id
    )
    if status:
        query = query.filter(bulk_models.WorkforceBulkOperation.status == status)
    if operation_type:
        query = query.filter(bulk_models.WorkforceBulkOperation.operation_type == operation_type)
    total = query.count()
    rows = query.order_by(
        bulk_models.WorkforceBulkOperation.created_at.desc(),
        bulk_models.WorkforceBulkOperation.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size).all()
    return bulk_schemas.BulkOperationsPage(
        items=[_operation_read(row) for row in rows], page=page, page_size=page_size,
        total=total, pages=math.ceil(total / page_size) if total else 0,
    )


def list_items(db: Session, *, amo_id: str, operation_id: str, page: int, page_size: int, status=None):
    if get_operation(db, amo_id=amo_id, operation_id=operation_id) is None:
        raise ValueError("Bulk operation not found")
    query = db.query(bulk_models.WorkforceBulkOperationItem).filter(
        bulk_models.WorkforceBulkOperationItem.operation_id == operation_id,
        bulk_models.WorkforceBulkOperationItem.amo_id == amo_id,
    )
    if status:
        query = query.filter(bulk_models.WorkforceBulkOperationItem.status == status)
    total = query.count()
    rows = query.order_by(bulk_models.WorkforceBulkOperationItem.sequence.asc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    users = {str(row.id): row for row in db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id.in_([item.user_id for item in rows] or ["__none__"]),
    ).all()}
    return bulk_schemas.BulkOperationItemsPage(
        items=[bulk_schemas.BulkOperationItemRead(
            id=str(item.id), user_id=str(item.user_id),
            staff_code=getattr(users.get(str(item.user_id)), "staff_code", None),
            full_name=getattr(users.get(str(item.user_id)), "full_name", None),
            status=item.status, attempt_count=item.attempt_count,
            outcome_code=item.outcome_code, outcome_message=item.outcome_message,
            result=item.result_json, started_at=item.started_at, completed_at=item.completed_at,
        ) for item in rows],
        page=page, page_size=page_size, total=total,
        pages=math.ceil(total / page_size) if total else 0,
    )


def failure_report_csv(db: Session, *, amo_id: str, operation_id: str) -> str:
    if get_operation(db, amo_id=amo_id, operation_id=operation_id) is None:
        raise ValueError("Bulk operation not found")
    rows = db.query(bulk_models.WorkforceBulkOperationItem).filter(
        bulk_models.WorkforceBulkOperationItem.operation_id == operation_id,
        bulk_models.WorkforceBulkOperationItem.amo_id == amo_id,
        bulk_models.WorkforceBulkOperationItem.status == "FAILED",
    ).order_by(bulk_models.WorkforceBulkOperationItem.sequence.asc()).all()
    users = {str(row.id): row for row in db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id.in_([item.user_id for item in rows] or ["__none__"]),
    ).all()}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User ID", "Staff number", "Name", "Failure code", "Failure reason", "Attempts"])
    for item in rows:
        user = users.get(str(item.user_id))
        writer.writerow([item.user_id, getattr(user, "staff_code", None),
                         getattr(user, "full_name", None), item.outcome_code,
                         item.outcome_message, item.attempt_count])
    return output.getvalue()


def retry_failed_operation(db: Session, *, amo_id: str, actor, operation_id: str, idempotency_key: str):
    source = get_operation(db, amo_id=amo_id, operation_id=operation_id)
    if source is None:
        raise ValueError("Bulk operation not found")
    if source.status not in {"COMPLETED_WITH_ERRORS", "FAILED"}:
        raise ValueError("Only failed or partially failed operations can be retried")
    failed = db.query(bulk_models.WorkforceBulkOperationItem).filter(
        bulk_models.WorkforceBulkOperationItem.operation_id == source.id,
        bulk_models.WorkforceBulkOperationItem.status == "FAILED",
    ).order_by(bulk_models.WorkforceBulkOperationItem.sequence.asc()).all()
    if not failed:
        raise ValueError("This operation has no failed records to retry")
    user_ids = [str(item.user_id) for item in failed]
    item_inputs = {str(item.user_id): item.input_json for item in failed if item.input_json is not None}
    row, created = _create_operation(
        db, amo_id=amo_id, actor_user_id=str(actor.id), operation_type=source.operation_type,
        idempotency_key=idempotency_key,
        selection_token=_canonical_hash({"source": str(source.id), "failed_user_ids": user_ids}),
        user_ids=user_ids,
        selection_snapshot={"mode": "EXPLICIT", "user_ids": user_ids,
                            "retry_source": str(source.id)},
        payload_json=source.payload_json, item_inputs=item_inputs,
        retry_of_operation_id=str(source.id),
    )
    return _operation_read(row), created


def resume_operation(db: Session, *, amo_id: str, actor, operation_id: str):
    row = db.query(bulk_models.WorkforceBulkOperation).filter(
        bulk_models.WorkforceBulkOperation.amo_id == amo_id,
        bulk_models.WorkforceBulkOperation.id == operation_id,
    ).with_for_update().first()
    if row is None:
        raise ValueError("Bulk operation not found")
    if row.status in {"COMPLETED", "COMPLETED_WITH_ERRORS"}:
        raise ValueError("Completed operations cannot be resumed; retry only their failed records")
    if row.status == "RUNNING":
        heartbeat = row.heartbeat_at or row.started_at or row.created_at
        if heartbeat and (_utcnow() - heartbeat).total_seconds() < 300:
            raise ValueError("This operation is still active and does not need to be resumed")
    if str(row.actor_user_id) != str(actor.id) and not getattr(actor, "is_amo_admin", False) and not getattr(actor, "is_superuser", False):
        raise ValueError("Only the initiating administrator or a tenant administrator may resume this operation")
    db.query(bulk_models.WorkforceBulkOperationItem).filter(
        bulk_models.WorkforceBulkOperationItem.operation_id == row.id,
        bulk_models.WorkforceBulkOperationItem.status == "RUNNING",
    ).update({
        bulk_models.WorkforceBulkOperationItem.status: "PENDING",
        bulk_models.WorkforceBulkOperationItem.outcome_code: "RESUMED_AFTER_INTERRUPTION",
        bulk_models.WorkforceBulkOperationItem.outcome_message: "The interrupted record was returned to the processing queue",
        bulk_models.WorkforceBulkOperationItem.completed_at: None,
    }, synchronize_session=False)
    row.status = "QUEUED"
    row.last_error = None
    row.completed_at = None
    row.heartbeat_at = _utcnow()
    audit_services.log_event(
        db, amo_id=amo_id, actor_user_id=str(actor.id),
        entity_type="WorkforceBulkOperation", entity_id=str(row.id), action="resume",
        correlation_id=str(row.id), after={"status": "QUEUED",
        "processed_count": row.processed_count}, metadata={"module": "workforce"},
    )
    db.flush()
    return _operation_read(row)
