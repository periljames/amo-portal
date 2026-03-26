from __future__ import annotations

from datetime import datetime
import logging
from typing import Optional, Sequence

from amodb.apps.events.broker import EventEnvelope, publish_event

import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from . import models, schemas

logger = logging.getLogger(__name__)


def create_audit_event(
    db: Session,
    *,
    amo_id: str,
    data: schemas.AuditEventCreate,
) -> models.AuditEvent:
    before_payload = data.before
    after_payload = data.after
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
        with db.begin_nested():
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
            metadata_payload = {"amoId": amo_id, **(event.metadata_json or {})}
            event_type = f"{event.entity_type}.{event.action}".lower()
            if metadata_payload.get("module") == "training":
                event_type = f"training.{event.entity_type}.{event.action}".lower()
            envelope = EventEnvelope(
                id=str(event.id),
                type=event_type,
                entityType=event.entity_type,
                entityId=event.entity_id,
                action=event.action,
                timestamp=event.occurred_at.isoformat() if event.occurred_at else event.created_at.isoformat(),
                actor={"userId": actor_user_id} if actor_user_id else None,
                metadata=metadata_payload,
            )
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
            exc_info=True,
        )
        if critical:
            raise
        return None
    try:
        publish_event(envelope)
    except Exception:
        logger.warning(
            "Failed to publish audit event",
            extra={
                "amo_id": amo_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
            },
            exc_info=True,
        )
        if critical:
            raise
    return event


def list_audit_events(
    db: Session,
    *,
    amo_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[models.AuditEvent | dict]:
    try:
        query = db.query(models.AuditEvent).filter(models.AuditEvent.amo_id == amo_id)
        if entity_type:
            query = query.filter(models.AuditEvent.entity_type == entity_type)
        if entity_id:
            query = query.filter(models.AuditEvent.entity_id == entity_id)
        if action:
            query = query.filter(models.AuditEvent.action == action)
        if start:
            query = query.filter(models.AuditEvent.occurred_at >= start)
        if end:
            query = query.filter(models.AuditEvent.occurred_at <= end)
        return query.order_by(models.AuditEvent.occurred_at.desc()).limit(limit).offset(offset).all()
    except ProgrammingError as exc:
        if _is_missing_audit_column_error(exc):
            return _list_audit_events_with_legacy_columns(
                db,
                amo_id=amo_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                start=start,
                end=end,
                limit=limit,
                offset=offset,
            )
        raise


def _is_missing_audit_column_error(exc: Exception) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return "undefined column" in message and "audit_events" in message


def _list_audit_events_with_legacy_columns(
    db: Session,
    *,
    amo_id: str,
    entity_type: Optional[str],
    entity_id: Optional[str],
    action: Optional[str],
    start: Optional[datetime],
    end: Optional[datetime],
    limit: int,
    offset: int,
) -> Sequence[dict]:
    bind = db.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("audit_events")}

    before_col = (
        sa.literal_column("before")
        if "before" in columns
        else sa.literal_column("before_json")
        if "before_json" in columns
        else sa.null()
    )
    after_col = (
        sa.literal_column("after")
        if "after" in columns
        else sa.literal_column("after_json")
        if "after_json" in columns
        else sa.null()
    )
    metadata_col = sa.literal_column("metadata") if "metadata" in columns else sa.null()

    params: dict[str, object] = {"amo_id": amo_id}
    if entity_type:
        params["entity_type"] = entity_type
    if entity_id:
        params["entity_id"] = entity_id
    if action:
        params["action"] = action
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    params["limit"] = limit
    params["offset"] = offset

    audit_table = sa.table(
        "audit_events",
        sa.column("id"),
        sa.column("amo_id"),
        sa.column("entity_type"),
        sa.column("entity_id"),
        sa.column("action"),
        sa.column("actor_user_id"),
        sa.column("occurred_at"),
        sa.column("correlation_id"),
        sa.column("created_at"),
    )
    filters = [audit_table.c.amo_id == sa.bindparam("amo_id")]
    if entity_type:
        filters.append(audit_table.c.entity_type == sa.bindparam("entity_type"))
    if entity_id:
        filters.append(audit_table.c.entity_id == sa.bindparam("entity_id"))
    if action:
        filters.append(audit_table.c.action == sa.bindparam("action"))
    if start:
        filters.append(audit_table.c.occurred_at >= sa.bindparam("start"))
    if end:
        filters.append(audit_table.c.occurred_at <= sa.bindparam("end"))

    query = (
        sa.select(
            audit_table.c.id,
            audit_table.c.amo_id,
            audit_table.c.entity_type,
            audit_table.c.entity_id,
            audit_table.c.action,
            audit_table.c.actor_user_id,
            audit_table.c.occurred_at,
            before_col.label("before"),
            after_col.label("after"),
            audit_table.c.correlation_id,
            metadata_col.label("metadata_json"),
            audit_table.c.created_at,
        )
        .where(*filters)
        .order_by(audit_table.c.occurred_at.desc())
        .limit(sa.bindparam("limit"))
        .offset(sa.bindparam("offset"))
    )
    return [dict(row) for row in db.execute(query, params).mappings().all()]
