from __future__ import annotations

from datetime import datetime
import logging
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from . import models, schemas

logger = logging.getLogger(__name__)


def create_audit_event(
    db: Session,
    *,
    amo_id: str,
    data: schemas.AuditEventCreate,
) -> models.AuditEvent:
    before_payload = data.before if data.before is not None else data.before_json
    after_payload = data.after if data.after is not None else data.after_json
    event = models.AuditEvent(
        amo_id=amo_id,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        action=data.action,
        actor_user_id=data.actor_user_id,
        before=before_payload,
        after=after_payload,
        correlation_id=data.correlation_id,
        metadata_json=data.metadata,
    )
    if data.occurred_at is not None:
        event.occurred_at = data.occurred_at
    db.add(event)
    db.flush()
    return event


def log_event(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
    entity_type: str,
    entity_id: str,
    action: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    correlation_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    critical: bool = False,
) -> Optional[models.AuditEvent]:
    """
    Best-effort audit event logger.
    - For critical actions (publish/close/export), raise on failure.
    - For non-critical actions, log warning and continue.
    """
    try:
        event = create_audit_event(
            db,
            amo_id=amo_id,
            data=schemas.AuditEventCreate(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_user_id=actor_user_id,
                before=before,
                after=after,
                correlation_id=correlation_id,
                metadata=metadata,
            ),
        )
        return event
    except Exception:
        logger.warning(
            "Failed to log audit event",
            extra={
                "amo_id": amo_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "critical": critical,
            },
        )
        if critical:
            raise
        return None


def list_audit_events(
    db: Session,
    *,
    amo_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Sequence[models.AuditEvent]:
    query = db.query(models.AuditEvent).filter(models.AuditEvent.amo_id == amo_id)
    if entity_type:
        query = query.filter(models.AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(models.AuditEvent.entity_id == entity_id)
    if start:
        query = query.filter(models.AuditEvent.occurred_at >= start)
    if end:
        query = query.filter(models.AuditEvent.occurred_at <= end)
    return query.order_by(models.AuditEvent.occurred_at.desc()).all()
