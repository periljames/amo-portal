from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.apps.audit import models as audit_models
from amodb.apps.events.broker import EventEnvelope, publish_event
from amodb.database import get_read_db, get_write_db

from . import models
from .audit_checklist_execution_models import (
    QualityAuditChecklistExecutionEvent,
    QualityAuditChecklistExecutionGovernance,
    QualityAuditFieldworkMutationReceipt,
)
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit checklist execution governance"])

CanonicalResponse = Literal["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"]


class ChecklistExecutionUpdate(BaseModel):
    canonical_response_status: CanonicalResponse
    auditor_notes: str | None = Field(default=None, max_length=12000)
    evidence_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    reason: str = Field(min_length=8, max_length=4000)


class FieldworkMutation(BaseModel):
    client_mutation_id: str = Field(min_length=8, max_length=128)
    device_id: str = Field(min_length=8, max_length=128)
    device_sequence: int = Field(ge=0)
    base_version: int = Field(ge=0)
    operation: Literal["CHECKLIST_UPDATE"] = "CHECKLIST_UPDATE"
    canonical_response_status: CanonicalResponse
    auditor_notes: str | None = Field(default=None, max_length=12000)
    evidence_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    reason: str = Field(min_length=8, max_length=4000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_from_legacy(value: str | None) -> CanonicalResponse:
    normalized = str(value or "PENDING").upper()
    if normalized == "NON_CONFORMING":
        return "NONCOMPLIANT"
    if normalized in {"COMPLIANT", "OBSERVATION", "NOT_APPLICABLE"}:
        return normalized  # type: ignore[return-value]
    return "NOT_VERIFIED"


def _legacy_from_canonical(value: CanonicalResponse) -> str:
    if value == "NONCOMPLIANT":
        return "NON_CONFORMING"
    if value == "NOT_VERIFIED":
        return "PENDING"
    return value


def _item(db: Session, *, amo_id: str, audit_id: uuid.UUID, item_id: uuid.UUID, lock: bool = False) -> models.QualityAuditChecklistItem:
    query = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == amo_id,
        models.QualityAuditChecklistItem.audit_id == audit_id,
        models.QualityAuditChecklistItem.id == item_id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit checklist item not found.")
    return row


def _governance_snapshot(row: QualityAuditChecklistExecutionGovernance) -> dict[str, Any]:
    return {
        "canonical_response_status": row.canonical_response_status,
        "auditor_notes": row.auditor_notes,
        "evidence_references": list(row.evidence_references or []),
        "entity_version": int(row.entity_version or 1),
        "updated_by_user_id": row.updated_by_user_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _event_dict(row: QualityAuditChecklistExecutionEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "reason": row.reason,
        "before_snapshot": row.before_snapshot,
        "after_snapshot": row.after_snapshot,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at,
    }


def _row_dict(item: models.QualityAuditChecklistItem, governance: QualityAuditChecklistExecutionGovernance | None) -> dict[str, Any]:
    canonical = governance.canonical_response_status if governance else _canonical_from_legacy(item.response_status)
    return {
        "checklist_item_id": str(item.id),
        "audit_id": str(item.audit_id),
        "section": item.section,
        "checklist_ref": item.checklist_ref,
        "requirement_ref": item.requirement_ref,
        "prompt": item.prompt,
        "legacy_response_status": item.response_status,
        "canonical_response_status": canonical,
        "objective_evidence": item.objective_evidence,
        "finding_id": str(item.finding_id) if item.finding_id else None,
        "auditor_notes": governance.auditor_notes if governance else None,
        "evidence_references": list(governance.evidence_references or []) if governance else [],
        "governance_id": str(governance.id) if governance else None,
        "entity_version": int(governance.entity_version or 1) if governance else 0,
        "updated_by_user_id": governance.updated_by_user_id if governance else item.completed_by_user_id,
        "updated_at": governance.updated_at if governance else item.updated_at,
        "events": [_event_dict(event) for event in list(governance.events or [])] if governance else [],
    }


def _apply_execution_update(
    db: Session,
    *,
    ctx: TenantContext,
    item: models.QualityAuditChecklistItem,
    payload: ChecklistExecutionUpdate,
    governance: QualityAuditChecklistExecutionGovernance | None,
) -> QualityAuditChecklistExecutionGovernance:
    event_type = "UPDATED"
    before_snapshot: dict[str, Any] | None
    if governance is None:
        event_type = "CREATED"
        before_snapshot = {
            "canonical_response_status": _canonical_from_legacy(item.response_status),
            "auditor_notes": None,
            "evidence_references": [],
            "entity_version": 0,
            "legacy_response_status": item.response_status,
        }
        governance = QualityAuditChecklistExecutionGovernance(
            amo_id=ctx.amo_id,
            audit_id=item.audit_id,
            checklist_item_id=item.id,
            canonical_response_status=payload.canonical_response_status,
            auditor_notes=payload.auditor_notes.strip() if payload.auditor_notes else None,
            evidence_references=list(payload.evidence_references),
            entity_version=1,
            updated_by_user_id=ctx.user_id,
        )
        db.add(governance)
        db.flush()
    else:
        before_snapshot = _governance_snapshot(governance)
        governance.canonical_response_status = payload.canonical_response_status
        governance.auditor_notes = payload.auditor_notes.strip() if payload.auditor_notes else None
        governance.evidence_references = list(payload.evidence_references)
        governance.entity_version = int(governance.entity_version or 1) + 1
        governance.updated_by_user_id = ctx.user_id
        governance.updated_at = _utcnow()

    legacy_status = _legacy_from_canonical(payload.canonical_response_status)
    item.response_status = legacy_status
    if payload.canonical_response_status == "NOT_VERIFIED":
        item.completed_by_user_id = None
        item.completed_at = None
    else:
        item.completed_by_user_id = ctx.user_id
        item.completed_at = _utcnow()
    item.updated_at = _utcnow()

    after_snapshot = {
        **_governance_snapshot(governance),
        "legacy_response_status": legacy_status,
        "objective_evidence": item.objective_evidence,
        "finding_id": str(item.finding_id) if item.finding_id else None,
    }
    db.add(QualityAuditChecklistExecutionEvent(
        amo_id=ctx.amo_id,
        audit_id=item.audit_id,
        checklist_item_id=item.id,
        governance_id=governance.id,
        event_type=event_type,
        reason=payload.reason.strip(),
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        actor_user_id=ctx.user_id,
    ))
    return governance


def _mutation_hash(payload: FieldworkMutation) -> str:
    encoded = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _publish_persisted_event(row: audit_models.AuditEvent) -> None:
    try:
        timestamp = (row.occurred_at or row.created_at or _utcnow()).isoformat()
        publish_event(EventEnvelope(
            id=str(row.id),
            type=f"{row.entity_type}.{row.action}".lower(),
            entityType=row.entity_type,
            entityId=row.entity_id,
            action=row.action,
            timestamp=timestamp,
            actor={"userId": row.actor_user_id} if row.actor_user_id else None,
            metadata={"amoId": row.amo_id, **(row.metadata_json or {})},
        ))
    except Exception:
        # The durable audit_events row is the replay source of truth. A transient
        # in-process publish failure must not turn a committed fieldwork write
        # into a false client failure or duplicate replay.
        return


@router.get("/audits/{audit_id}/checklist-execution-governance")
def list_checklist_execution_governance(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    items = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == ctx.amo_id,
        models.QualityAuditChecklistItem.audit_id == audit_id,
    ).order_by(models.QualityAuditChecklistItem.section.asc(), models.QualityAuditChecklistItem.sort_order.asc()).limit(1000).all()
    governance_rows = db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == ctx.amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
    ).all()
    by_item = {row.checklist_item_id: row for row in governance_rows}
    return {
        "items": [_row_dict(item, by_item.get(item.id)) for item in items],
        "canonical_response_values": ["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"],
        "legacy_compatibility": {
            "NONCOMPLIANT": "NON_CONFORMING",
            "NOT_VERIFIED": "PENDING",
        },
    }


@router.patch("/audits/{audit_id}/checklist-items/{item_id}/execution-governance")
def update_checklist_execution_governance(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ChecklistExecutionUpdate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    item = _item(db, amo_id=ctx.amo_id, audit_id=audit_id, item_id=item_id, lock=True)
    governance = db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == ctx.amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
        QualityAuditChecklistExecutionGovernance.checklist_item_id == item_id,
    ).with_for_update().first()

    governance = _apply_execution_update(db, ctx=ctx, item=item, payload=payload, governance=governance)
    db.commit()
    governance = db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(QualityAuditChecklistExecutionGovernance.id == governance.id).one()
    return _row_dict(item, governance)


@router.post("/audits/{audit_id}/checklist-items/{item_id}/fieldwork-mutations")
def mutate_live_fieldwork(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: FieldworkMutation,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Apply one replay-safe Live Audit checklist mutation.

    The client mutation id is the durable idempotency key. ``base_version``
    provides optimistic concurrency so an offline device cannot silently
    overwrite a newer controlled fieldwork decision. The committed audit event
    is written in the same transaction and then published over the existing
    portal SSE broker after commit; reconnect replay remains authoritative if
    the in-process publish is unavailable.
    """

    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    payload_hash = _mutation_hash(payload)

    existing = db.query(QualityAuditFieldworkMutationReceipt).filter(
        QualityAuditFieldworkMutationReceipt.amo_id == ctx.amo_id,
        QualityAuditFieldworkMutationReceipt.client_mutation_id == payload.client_mutation_id,
    ).first()
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "FIELDWORK_IDEMPOTENCY_CONFLICT",
                    "message": "This client mutation id was already used with different fieldwork content.",
                    "client_mutation_id": payload.client_mutation_id,
                },
            )
        return {
            "client_mutation_id": payload.client_mutation_id,
            "committed_version": existing.committed_version,
            "replayed": True,
            "row": existing.result_snapshot,
        }

    item = _item(db, amo_id=ctx.amo_id, audit_id=audit_id, item_id=item_id, lock=True)
    governance = db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == ctx.amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
        QualityAuditChecklistExecutionGovernance.checklist_item_id == item_id,
    ).with_for_update().first()

    current_version = int(governance.entity_version or 1) if governance is not None else 0
    if payload.base_version != current_version:
        server_row = jsonable_encoder(_row_dict(item, governance))
        raise HTTPException(
            status_code=409,
            detail={
                "code": "FIELDWORK_VERSION_CONFLICT",
                "message": "This checklist item changed after the device copy was read. Review the server version before retrying.",
                "client_mutation_id": payload.client_mutation_id,
                "base_version": payload.base_version,
                "server_version": current_version,
                "server_row": server_row,
            },
        )

    update = ChecklistExecutionUpdate(
        canonical_response_status=payload.canonical_response_status,
        auditor_notes=payload.auditor_notes,
        evidence_references=payload.evidence_references,
        reason=payload.reason,
    )
    governance = _apply_execution_update(db, ctx=ctx, item=item, payload=update, governance=governance)
    committed_version = int(governance.entity_version or 1)
    db.flush()

    row_snapshot = jsonable_encoder(_row_dict(item, governance))
    receipt = QualityAuditFieldworkMutationReceipt(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        checklist_item_id=item_id,
        client_mutation_id=payload.client_mutation_id,
        device_id=payload.device_id,
        device_sequence=payload.device_sequence,
        base_version=payload.base_version,
        committed_version=committed_version,
        operation=payload.operation,
        payload_hash=payload_hash,
        result_snapshot=row_snapshot,
        actor_user_id=ctx.user_id,
    )
    db.add(receipt)

    realtime_event = audit_models.AuditEvent(
        amo_id=ctx.amo_id,
        entity_type="qms.audit.checklist_item",
        entity_id=str(item_id),
        action="UPDATED",
        actor_user_id=ctx.user_id,
        before={"entity_version": current_version},
        after={
            "entity_version": committed_version,
            "canonical_response_status": payload.canonical_response_status,
        },
        correlation_id=payload.client_mutation_id,
        metadata_json={
            "module": "quality",
            "auditId": str(audit_id),
            "checklistItemId": str(item_id),
            "clientMutationId": payload.client_mutation_id,
            "deviceId": payload.device_id,
            "deviceSequence": payload.device_sequence,
            "entityVersion": committed_version,
        },
    )
    db.add(realtime_event)
    db.flush()
    db.commit()

    _publish_persisted_event(realtime_event)
    return {
        "client_mutation_id": payload.client_mutation_id,
        "committed_version": committed_version,
        "replayed": False,
        "row": row_snapshot,
    }
