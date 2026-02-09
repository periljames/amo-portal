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
        publish_event(
            EventEnvelope(
                id=str(event.id),
                type=f\"{event.entity_type}.{event.action}\".lower(),
                entityType=event.entity_type,
                entityId=event.entity_id,
                action=event.action,
                timestamp=event.occurred_at.isoformat() if event.occurred_at else event.created_at.isoformat(),
                actor={\"userId\": actor_user_id} if actor_user_id else None,
                metadata={\"amoId\": amo_id, **(event.metadata_json or {})},
            )
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
) -> Sequence[models.AuditEvent | dict]:
    try:
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
    except ProgrammingError as exc:
        if _is_missing_audit_column_error(exc):
            return _list_audit_events_with_legacy_columns(
                db,
                amo_id=amo_id,
                entity_type=entity_type,
                entity_id=entity_id,
                start=start,
                end=end,
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
    start: Optional[datetime],
    end: Optional[datetime],
) -> Sequence[dict]:
    bind = db.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("audit_events")}

    before_expr = "before" if "before" in columns else "before_json" if "before_json" in columns else "NULL"
    after_expr = "after" if "after" in columns else "after_json" if "after_json" in columns else "NULL"
    metadata_expr = "metadata" if "metadata" in columns else "NULL"

    where_clauses = ["amo_id = :amo_id"]
    params: dict[str, object] = {"amo_id": amo_id}
    if entity_type:
        where_clauses.append("entity_type = :entity_type")
        params["entity_type"] = entity_type
    if entity_id:
        where_clauses.append("entity_id = :entity_id")
        params["entity_id"] = entity_id
    if start:
        where_clauses.append("occurred_at >= :start")
        params["start"] = start
    if end:
        where_clauses.append("occurred_at <= :end")
        params["end"] = end

    sql = sa.text(
        """
        SELECT
            id,
            amo_id,
            entity_type,
            entity_id,
            action,
            actor_user_id,
            occurred_at,
            {before_expr} AS before,
            {after_expr} AS after,
            correlation_id,
            {metadata_expr} AS metadata_json,
            created_at
        FROM audit_events
        WHERE {where_clause}
        ORDER BY occurred_at DESC
        """.format(
            before_expr=before_expr,
            after_expr=after_expr,
            metadata_expr=metadata_expr,
            where_clause=" AND ".join(where_clauses),
        )
    )
    return [dict(row) for row in db.execute(sql, params).mappings().all()]
