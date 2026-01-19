from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from . import models, schemas


def create_audit_event(
    db: Session,
    *,
    amo_id: str,
    data: schemas.AuditEventCreate,
) -> models.AuditEvent:
    event = models.AuditEvent(
        amo_id=amo_id,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        action=data.action,
        actor_user_id=data.actor_user_id,
        before_json=data.before_json,
        after_json=data.after_json,
        correlation_id=data.correlation_id,
    )
    if data.occurred_at is not None:
        event.occurred_at = data.occurred_at
    db.add(event)
    db.flush()
    return event


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
