from __future__ import annotations

import hashlib
import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import ReplayCommand

TERMINAL = {"SUCCEEDED", "CONFLICT", "REJECTED", "FAILED"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def request_hash(payload: Any) -> str:
    encoded = jsonable_encoder(payload)
    raw = json.dumps(encoded, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommandClaim:
    row: ReplayCommand
    replayed: bool


class CommandConflict(ValueError):
    pass


def begin_command(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    method: str,
    route_key: str,
    idempotency_key: str,
    payload: Any,
    expected_revision: str | int | None = None,
) -> CommandClaim:
    key = (idempotency_key or "").strip()
    if not key or len(key) > 128:
        raise CommandConflict("A valid Idempotency-Key is required for replayable commands")
    digest = request_hash(payload)
    query = db.query(ReplayCommand).filter(
        ReplayCommand.amo_id == amo_id,
        ReplayCommand.actor_user_id == actor_user_id,
        ReplayCommand.method == method.upper(),
        ReplayCommand.route_key == route_key,
        ReplayCommand.idempotency_key == key,
    )
    existing = query.with_for_update().first()
    if existing is not None:
        if existing.request_hash != digest:
            raise CommandConflict("Idempotency-Key was already used with a different request")
        existing.attempt_count += 1
        if existing.status in TERMINAL:
            return CommandClaim(existing, True)
        if existing.lease_expires_at and existing.lease_expires_at > _utcnow():
            return CommandClaim(existing, True)
        existing.lease_owner = f"{socket.gethostname()}:{os.getpid()}"
        existing.lease_expires_at = _utcnow() + timedelta(seconds=60)
        return CommandClaim(existing, False)

    row = ReplayCommand(
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        method=method.upper(),
        route_key=route_key,
        idempotency_key=key,
        request_hash=digest,
        expected_revision=None if expected_revision is None else str(expected_revision),
        status="PROCESSING",
        lease_owner=f"{socket.gethostname()}:{os.getpid()}",
        lease_expires_at=_utcnow() + timedelta(seconds=60),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise CommandConflict("The command is already being processed; query its status before retrying") from exc
    return CommandClaim(row, False)


def complete_command(row: ReplayCommand, *, response: Any, status_code: int) -> None:
    row.status = "SUCCEEDED"
    row.response_status = status_code
    row.response_json = jsonable_encoder(response)
    row.error_code = None
    row.error_detail = None
    row.completed_at = _utcnow()
    row.lease_expires_at = None


def fail_command(row: ReplayCommand, *, status: str, error_code: str, detail: str, response_status: int) -> None:
    if status not in {"CONFLICT", "REJECTED", "FAILED"}:
        raise ValueError("Invalid terminal command status")
    row.status = status
    row.response_status = response_status
    row.error_code = error_code
    row.error_detail = detail[:4000]
    row.completed_at = _utcnow()
    row.lease_expires_at = None


def status_payload(row: ReplayCommand) -> dict[str, Any]:
    return {
        "id": row.id,
        "idempotency_key": row.idempotency_key,
        "method": row.method,
        "route_key": row.route_key,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "response_status": row.response_status,
        "response": row.response_json,
        "error_code": row.error_code,
        "error_detail": row.error_detail,
        "updated_at": row.updated_at,
        "completed_at": row.completed_at,
    }
