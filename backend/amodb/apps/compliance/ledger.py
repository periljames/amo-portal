from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sign(payload_hash: str) -> tuple[str | None, str | None]:
    secret = (os.getenv("COMPLIANCE_LEDGER_HMAC_SECRET") or "").strip()
    if not secret:
        return None, None
    signature = hmac.new(secret.encode("utf-8"), payload_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return "HMAC-SHA256", signature


def _latest_hash_for_amo(db: Session, amo_id: str) -> str | None:
    row = db.execute(
        text("SELECT payload_hash_sha256 FROM compliance_event_ledger WHERE amo_id = :amo_id ORDER BY occurred_at DESC LIMIT 1"),
        {"amo_id": amo_id},
    ).first()
    return str(row[0]) if row else None


def write_ledger_event(
    db: Session,
    *,
    amo_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_user_id: str | None,
    payload: dict[str, Any],
    critical: bool = True,
    fail_closed: bool = True,
) -> str:
    event_id = str(uuid.uuid4())
    payload_json = _canonical_json(payload)
    payload_hash = _sha256_hex(payload_json)
    prev_hash = _latest_hash_for_amo(db, amo_id)
    signature_alg, signature_value = _sign(payload_hash)
    try:
        db.execute(
            text(
                """
                INSERT INTO compliance_event_ledger (
                    id, amo_id, entity_type, entity_id, action, actor_user_id,
                    occurred_at, payload_json, payload_hash_sha256, prev_hash_sha256,
                    signature_alg, signature_value, critical
                ) VALUES (
                    :id, :amo_id, :entity_type, :entity_id, :action, :actor_user_id,
                    :occurred_at, CAST(:payload_json AS json), :payload_hash_sha256, :prev_hash_sha256,
                    :signature_alg, :signature_value, :critical
                )
                """
            ),
            {
                "id": event_id,
                "amo_id": amo_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "actor_user_id": actor_user_id,
                "occurred_at": _utcnow(),
                "payload_json": payload_json,
                "payload_hash_sha256": payload_hash,
                "prev_hash_sha256": prev_hash,
                "signature_alg": signature_alg,
                "signature_value": signature_value,
                "critical": critical,
            },
        )
        return event_id
    except Exception:
        if fail_closed:
            raise
        return event_id
