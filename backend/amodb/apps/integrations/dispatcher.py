from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from amodb.database import WriteSessionLocal

from . import models
from .services import _sign_payload


DEFAULT_LIMIT = int(os.getenv("INTEGRATION_DISPATCH_LIMIT", "50"))
DEFAULT_INTERVAL_SEC = int(os.getenv("INTEGRATION_DISPATCH_INTERVAL_SEC", "5"))
MAX_ATTEMPTS = int(os.getenv("INTEGRATION_DISPATCH_MAX_ATTEMPTS", "5"))
BASE_BACKOFF_SEC = int(os.getenv("INTEGRATION_DISPATCH_BACKOFF_SEC", "5"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_next_attempt(now: datetime, attempt: int) -> datetime:
    backoff = BASE_BACKOFF_SEC * (2 ** max(attempt - 1, 0))
    return now + timedelta(seconds=backoff)


def _post_event(url: str, payload: dict, signature: Optional[str]) -> Tuple[int, str]:
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if signature:
        req.add_header("X-Signature", signature)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def _load_config(db: Session, event: models.IntegrationOutboundEvent) -> Optional[models.IntegrationConfig]:
    config = (
        db.query(models.IntegrationConfig)
        .filter(models.IntegrationConfig.id == event.integration_id)
        .first()
    )
    if not config:
        return None
    if config.amo_id != event.amo_id:
        return None
    if not config.enabled or config.status != models.IntegrationConfigStatus.ACTIVE:
        return None
    return config


def dispatch_due_events(db: Session, *, now: Optional[datetime] = None, limit: int = DEFAULT_LIMIT) -> int:
    now = now or _utcnow()
    query = (
        db.query(models.IntegrationOutboundEvent)
        .filter(
            models.IntegrationOutboundEvent.status.in_(
                [
                    models.IntegrationOutboundStatus.PENDING,
                    models.IntegrationOutboundStatus.FAILED,
                ]
            ),
            models.IntegrationOutboundEvent.next_attempt_at <= now,
        )
        .order_by(models.IntegrationOutboundEvent.next_attempt_at.asc())
    )

    try:
        query = query.with_for_update(skip_locked=True)
    except Exception:
        pass

    events = query.limit(limit).all()
    if not events:
        return 0

    for event in events:
        attempt = event.attempt_count + 1
        config = _load_config(db, event)
        if not config:
            event.status = models.IntegrationOutboundStatus.FAILED
            event.last_error = "Integration config inactive or mismatched."
            event.attempt_count = attempt
            event.next_attempt_at = _compute_next_attempt(now, attempt)
            if attempt >= MAX_ATTEMPTS:
                event.status = models.IntegrationOutboundStatus.DEAD_LETTER
            continue

        if not config.base_url:
            event.status = models.IntegrationOutboundStatus.FAILED
            event.last_error = "Integration base_url is not configured."
            event.attempt_count = attempt
            event.next_attempt_at = _compute_next_attempt(now, attempt)
            if attempt >= MAX_ATTEMPTS:
                event.status = models.IntegrationOutboundStatus.DEAD_LETTER
            continue

        payload = {
            "event_type": event.event_type,
            "payload": event.payload_json,
            "event_id": event.id,
            "amo_id": event.amo_id,
        }
        signature = None
        if config.signing_secret:
            signature = _sign_payload(json.dumps(payload, sort_keys=True).encode("utf-8"), config.signing_secret)

        status_code, body = _post_event(config.base_url, payload, signature)
        if 200 <= status_code < 300:
            event.status = models.IntegrationOutboundStatus.SENT
            event.last_error = None
            event.attempt_count = attempt
            event.next_attempt_at = None
        else:
            event.status = models.IntegrationOutboundStatus.FAILED
            event.last_error = body[:500] if body else "Non-success response"
            event.attempt_count = attempt
            event.next_attempt_at = _compute_next_attempt(now, attempt)
            if attempt >= MAX_ATTEMPTS:
                event.status = models.IntegrationOutboundStatus.DEAD_LETTER

    db.commit()
    return len(events)


def run_dispatch_loop() -> None:
    while True:
        db = WriteSessionLocal()
        try:
            dispatched = dispatch_due_events(db)
        except Exception:
            db.rollback()
            dispatched = 0
        finally:
            db.close()
        time.sleep(DEFAULT_INTERVAL_SEC if dispatched == 0 else 0)


if __name__ == "__main__":
    run_dispatch_loop()
