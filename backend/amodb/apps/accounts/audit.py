"""Shared billing audit helpers.

Provides a small wrapper around the BillingAuditLog model so other services
can emit durable audit entries without duplicating boilerplate (JSON encoding,
commit behaviour, and best-effort fallbacks).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from . import models


def _serialise_details(details: Any) -> str:
    """Normalise detail payloads to a string for persistence."""
    if details is None:
        return ""
    if isinstance(details, (dict, list)):
        try:
            return json.dumps(details, sort_keys=True)
        except Exception:
            # Fall back to repr if the payload is not JSON serialisable.
            return repr(details)
    return str(details)


def record_audit_event(
    db: Session, *, amo_id: Optional[str], event: str, details: Any
) -> models.BillingAuditLog:
    """Persist a billing audit event."""
    log = models.BillingAuditLog(
        amo_id=amo_id,
        event_type=event,
        details=_serialise_details(details),
    )
    db.add(log)
    db.commit()
    return log


def safe_record_audit_event(
    db: Session, *, amo_id: Optional[str], event: str, details: Any
) -> Optional[models.BillingAuditLog]:
    """
    Best-effort audit logger.

    Audit failures should never block the main workflow, so this helper
    rolls back the failed transaction and returns None when something
    goes wrong.
    """
    try:
        return record_audit_event(db, amo_id=amo_id, event=event, details=details)
    except Exception:
        db.rollback()
        return None
