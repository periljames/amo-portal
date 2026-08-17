from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone

from ...database import get_db
from ...security import get_current_active_user
from ..accounts.models import User
from .command_service import status_payload
from .models import ReplayCommand
from ..workforce.bulk_models import WorkforceBulkOperation

router = APIRouter(prefix="/resilience", tags=["resilience"])


@router.get("/commands/{idempotency_key}")
def command_status(
    idempotency_key: str,
    method: str = Query(..., min_length=3, max_length=12),
    route_key: str = Query(..., min_length=1, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    row = db.query(ReplayCommand).filter(
        ReplayCommand.amo_id == current_user.effective_amo_id,
        ReplayCommand.actor_user_id == current_user.id,
        ReplayCommand.method == method.upper(),
        ReplayCommand.route_key == route_key,
        ReplayCommand.idempotency_key == idempotency_key,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail={"error_code": "COMMAND_NOT_FOUND", "retryable": True})
    return status_payload(row)


@router.get("/metrics")
def tenant_resilience_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    now = datetime.now(timezone.utc)
    oldest_bulk = db.query(func.min(WorkforceBulkOperation.created_at)).filter(
        WorkforceBulkOperation.amo_id == current_user.effective_amo_id,
        WorkforceBulkOperation.status.in_(("QUEUED", "RUNNING")),
    ).scalar()
    oldest_command = db.query(func.min(ReplayCommand.created_at)).filter(
        ReplayCommand.amo_id == current_user.effective_amo_id,
        ReplayCommand.status == "PROCESSING",
    ).scalar()

    def age(value) -> float:
        if value is None:
            return 0.0
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0.0, (now - value).total_seconds())

    return {
        "bulk_queue_age_seconds": age(oldest_bulk),
        "command_processing_age_seconds": age(oldest_command),
    }
