from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.events.broker import EventEnvelope, publish_event
from amodb.database import get_read_db, get_write_db

from . import models
from .audit_checklist_execution_models import (
    QualityAuditChecklistExecutionEvent,
    QualityAuditChecklistExecutionGovernance,
    QualityAuditFieldworkMutationReceipt,
)
from .enums import FindingLevel, QMSAuditStatus, QMSFindingSeverity, QMSFindingType
from .service import compute_target_close_date, normalize_finding_level
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit checklist execution governance"])

CanonicalResponse = Literal["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"]
FindingResponse = Literal["NONCOMPLIANT", "OBSERVATION"]


class ChecklistExecutionUpdate(BaseModel):
    canonical_response_status: CanonicalResponse
    auditor_notes: str | None = Field(default=None, max_length=12000)
    evidence_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    reason: str = Field(min_length=8, max_length=4000)


class FieldworkMutation(BaseModel):
    client_mutation_id: str = Field(min_length=8, max_length=128)
    device_id: str = Field(min_length=8, max_length=128)
    device_sequence: int = Field(ge=0)
    client_timestamp: datetime
    base_version: int = Field(ge=0)
    operation: Literal["CHECKLIST_UPDATE"] = "CHECKLIST_UPDATE"
    canonical_response_status: CanonicalResponse
    auditor_notes: str | None = Field(default=None, max_length=12000)
    evidence_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    reason: str = Field(min_length=8, max_length=4000)


class FieldworkFindingMutation(BaseModel):
    client_mutation_id: str = Field(min_length=8, max_length=128)
    device_id: str = Field(min_length=8, max_length=128)
    device_sequence: int = Field(ge=0)
    client_timestamp: datetime
    base_version: int = Field(ge=0)
    operation: Literal["CREATE_FINDING"] = "CREATE_FINDING"
    canonical_response_status: FindingResponse
    severity: QMSFindingSeverity
    level: FindingLevel
    requirement_ref: str | None = Field(default=None, max_length=255)
    description: str = Field(min_length=8, max_length=12000)
    objective_evidence: str | None = Field(default=None, max_length=12000)
    safety_sensitive: bool = False
    target_close_date: date | None = None
    auditor_notes: str | None = Field(default=None, max_length=12000)
    evidence_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    reason: str = Field(min_length=8, max_length=4000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_client_timestamp(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


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


def _mutation_hash(payload: BaseModel) -> str:
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
        return


def _internal_fieldwork_actor(db: Session, *, ctx: TenantContext, audit_id: uuid.UUID):
    from . import router as quality_router

    audit = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == ctx.amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).with_for_update().first()
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    user = db.query(account_models.User).filter(
        account_models.User.id == ctx.user_id,
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
    ).first()
    if user is None:
        raise HTTPException(status_code=403, detail="Active internal auditor identity is required.")
    quality_router._require_audit_fieldwork_write_access(user, audit)
    return audit, user, quality_router


def _finding_classification(payload: FieldworkFindingMutation) -> tuple[FindingLevel, QMSFindingType]:
    requested_type = QMSFindingType.OBSERVATION if payload.canonical_response_status == "OBSERVATION" else QMSFindingType.NON_CONFORMITY
    level = normalize_finding_level(payload.severity, payload.level, requested_type)
    finding_type = QMSFindingType.OBSERVATION if level == FindingLevel.LEVEL_4 else QMSFindingType.NON_CONFORMITY
    if payload.canonical_response_status == "OBSERVATION" and finding_type != QMSFindingType.OBSERVATION:
        raise HTTPException(status_code=422, detail="An OBSERVATION checklist response must use the governed Level 4 observation classification.")
    if payload.canonical_response_status == "NONCOMPLIANT" and finding_type != QMSFindingType.NON_CONFORMITY:
        raise HTTPException(status_code=422, detail="A NONCOMPLIANT checklist response must use a governed Level 1, 2 or 3 non-conformity classification.")
    return level, finding_type


def _existing_receipt_or_none(
    db: Session,
    *,
    ctx: TenantContext,
    client_mutation_id: str,
    payload_hash: str,
) -> QualityAuditFieldworkMutationReceipt | None:
    existing = db.query(QualityAuditFieldworkMutationReceipt).filter(
        QualityAuditFieldworkMutationReceipt.amo_id == ctx.amo_id,
        QualityAuditFieldworkMutationReceipt.client_mutation_id == client_mutation_id,
    ).first()
    if existing is not None and existing.payload_hash != payload_hash:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "FIELDWORK_IDEMPOTENCY_CONFLICT",
                "message": "This client mutation id was already used with different fieldwork content.",
                "client_mutation_id": client_mutation_id,
            },
        )
    return existing


def _locked_governance(
    db: Session,
    *,
    ctx: TenantContext,
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
) -> QualityAuditChecklistExecutionGovernance | None:
    return db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == ctx.amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
        QualityAuditChecklistExecutionGovernance.checklist_item_id == item_id,
    ).with_for_update().first()


def _assert_base_version(
    *,
    payload_base_version: int,
    client_mutation_id: str,
    item: models.QualityAuditChecklistItem,
    governance: QualityAuditChecklistExecutionGovernance | None,
) -> int:
    current_version = int(governance.entity_version or 1) if governance is not None else 0
    if payload_base_version != current_version:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "FIELDWORK_VERSION_CONFLICT",
                "message": "This checklist item changed after the device copy was read. Review the server version before retrying.",
                "client_mutation_id": client_mutation_id,
                "base_version": payload_base_version,
                "server_version": current_version,
                "server_row": jsonable_encoder(_row_dict(item, governance)),
            },
        )
    return current_version


def _fieldwork_event(
    *,
    ctx: TenantContext,
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    client_mutation_id: str,
    device_id: str,
    device_sequence: int,
    client_timestamp: datetime,
    current_version: int,
    committed_version: int,
    response: str,
) -> audit_models.AuditEvent:
    return audit_models.AuditEvent(
        amo_id=ctx.amo_id,
        entity_type="qms.audit.checklist_item",
        entity_id=str(item_id),
        action="UPDATED",
        actor_user_id=ctx.user_id,
        before={"entity_version": current_version},
        after={"entity_version": committed_version, "canonical_response_status": response},
        correlation_id=client_mutation_id,
        metadata_json={
            "module": "quality",
            "auditId": str(audit_id),
            "checklistItemId": str(item_id),
            "clientMutationId": client_mutation_id,
            "deviceId": device_id,
            "deviceSequence": device_sequence,
            "clientTimestamp": _normalise_client_timestamp(client_timestamp).isoformat(),
            "entityVersion": committed_version,
        },
    )


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
    governance = _locked_governance(db, ctx=ctx, audit_id=audit_id, item_id=item_id)
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
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _internal_fieldwork_actor(db, ctx=ctx, audit_id=audit_id)
    payload_hash = _mutation_hash(payload)
    existing = _existing_receipt_or_none(
        db,
        ctx=ctx,
        client_mutation_id=payload.client_mutation_id,
        payload_hash=payload_hash,
    )
    if existing is not None:
        return {
            "client_mutation_id": payload.client_mutation_id,
            "committed_version": existing.committed_version,
            "replayed": True,
            "row": existing.result_snapshot,
        }

    item = _item(db, amo_id=ctx.amo_id, audit_id=audit_id, item_id=item_id, lock=True)
    governance = _locked_governance(db, ctx=ctx, audit_id=audit_id, item_id=item_id)
    current_version = _assert_base_version(
        payload_base_version=payload.base_version,
        client_mutation_id=payload.client_mutation_id,
        item=item,
        governance=governance,
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
        client_timestamp=_normalise_client_timestamp(payload.client_timestamp),
        base_version=payload.base_version,
        committed_version=committed_version,
        operation=payload.operation,
        payload_hash=payload_hash,
        result_snapshot=row_snapshot,
        actor_user_id=ctx.user_id,
    )
    db.add(receipt)
    realtime_event = _fieldwork_event(
        ctx=ctx,
        audit_id=audit_id,
        item_id=item_id,
        client_mutation_id=payload.client_mutation_id,
        device_id=payload.device_id,
        device_sequence=payload.device_sequence,
        client_timestamp=payload.client_timestamp,
        current_version=current_version,
        committed_version=committed_version,
        response=payload.canonical_response_status,
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


@router.post("/audits/{audit_id}/checklist-items/{item_id}/fieldwork-findings")
def create_atomic_fieldwork_finding(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: FieldworkFindingMutation,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    payload_hash = _mutation_hash(payload)
    existing = _existing_receipt_or_none(
        db,
        ctx=ctx,
        client_mutation_id=payload.client_mutation_id,
        payload_hash=payload_hash,
    )
    if existing is not None:
        stored = dict(existing.result_snapshot or {})
        return {
            "client_mutation_id": payload.client_mutation_id,
            "committed_version": existing.committed_version,
            "replayed": True,
            **stored,
        }

    published_events: list[audit_models.AuditEvent] = []
    try:
        audit, _user, quality_router = _internal_fieldwork_actor(db, ctx=ctx, audit_id=audit_id)
        item = _item(db, amo_id=ctx.amo_id, audit_id=audit_id, item_id=item_id, lock=True)
        governance = _locked_governance(db, ctx=ctx, audit_id=audit_id, item_id=item_id)
        current_version = _assert_base_version(
            payload_base_version=payload.base_version,
            client_mutation_id=payload.client_mutation_id,
            item=item,
            governance=governance,
        )
        if item.finding_id is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "FIELDWORK_FINDING_ALREADY_LINKED",
                    "message": "This checklist item already has a governed finding. Review the existing finding before creating another.",
                    "finding_id": str(item.finding_id),
                },
            )

        level, finding_type = _finding_classification(payload)
        target_close_date = payload.target_close_date
        if target_close_date is None and level != FindingLevel.LEVEL_4:
            target_close_date = compute_target_close_date(level)

        finding = models.QMSAuditFinding(
            amo_id=audit.amo_id,
            audit_id=audit_id,
            finding_ref=quality_router._next_audit_finding_ref(db, audit),
            finding_type=finding_type,
            severity=payload.severity,
            level=level,
            requirement_ref=payload.requirement_ref.strip() if payload.requirement_ref else None,
            description=payload.description.strip(),
            objective_evidence=payload.objective_evidence.strip() if payload.objective_evidence else None,
            safety_sensitive=payload.safety_sensitive,
            target_close_date=target_close_date,
            created_by_user_id=ctx.user_id,
        )
        db.add(finding)
        db.flush()
        item.finding_id = finding.id

        if level != FindingLevel.LEVEL_4:
            task_owner = audit.lead_auditor_user_id or ctx.user_id
            quality_router.task_services.create_task(
                db,
                amo_id=ctx.amo_id,
                title="Respond to finding",
                description=f"Finding {finding.finding_ref or finding.id} requires response.",
                owner_user_id=task_owner,
                supervisor_user_id=audit.observer_auditor_user_id,
                due_at=quality_router._date_to_datetime(finding.target_close_date),
                entity_type="qms_finding",
                entity_id=str(finding.id),
                priority=2,
            )
            if audit.status in (QMSAuditStatus.PLANNED, QMSAuditStatus.IN_PROGRESS):
                audit.status = QMSAuditStatus.CAP_OPEN

        linked_car = quality_router._ensure_car_for_finding(
            db,
            audit=audit,
            finding=finding,
            requested_by_user_id=ctx.user_id,
        )

        execution_update = ChecklistExecutionUpdate(
            canonical_response_status=payload.canonical_response_status,
            auditor_notes=payload.auditor_notes,
            evidence_references=payload.evidence_references,
            reason=payload.reason,
        )
        governance = _apply_execution_update(
            db,
            ctx=ctx,
            item=item,
            payload=execution_update,
            governance=governance,
        )
        committed_version = int(governance.entity_version or 1)
        db.flush()

        row_snapshot = jsonable_encoder(_row_dict(item, governance))
        finding_snapshot = jsonable_encoder(quality_router._serialize_finding(finding))
        result_snapshot = {
            "row": row_snapshot,
            "finding": finding_snapshot,
            "car_id": str(linked_car.id) if linked_car else None,
            "car_number": linked_car.car_number if linked_car else None,
        }
        db.add(QualityAuditFieldworkMutationReceipt(
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            checklist_item_id=item_id,
            client_mutation_id=payload.client_mutation_id,
            device_id=payload.device_id,
            device_sequence=payload.device_sequence,
            client_timestamp=_normalise_client_timestamp(payload.client_timestamp),
            base_version=payload.base_version,
            committed_version=committed_version,
            operation=payload.operation,
            payload_hash=payload_hash,
            result_snapshot=result_snapshot,
            actor_user_id=ctx.user_id,
        ))

        finding_event = audit_models.AuditEvent(
            amo_id=ctx.amo_id,
            entity_type="qms.finding",
            entity_id=str(finding.id),
            action="CREATED",
            actor_user_id=ctx.user_id,
            after={
                "audit_id": str(audit_id),
                "finding_ref": finding.finding_ref,
                "severity": finding.severity.value,
                "level": finding.level.value,
                "target_close_date": str(finding.target_close_date) if finding.target_close_date else None,
                "checklist_item_id": str(item_id),
            },
            correlation_id=payload.client_mutation_id,
            metadata_json={
                "module": "quality",
                "auditId": str(audit_id),
                "checklistItemId": str(item_id),
                "clientMutationId": payload.client_mutation_id,
                "clientTimestamp": _normalise_client_timestamp(payload.client_timestamp).isoformat(),
            },
        )
        fieldwork_event = _fieldwork_event(
            ctx=ctx,
            audit_id=audit_id,
            item_id=item_id,
            client_mutation_id=payload.client_mutation_id,
            device_id=payload.device_id,
            device_sequence=payload.device_sequence,
            client_timestamp=payload.client_timestamp,
            current_version=current_version,
            committed_version=committed_version,
            response=payload.canonical_response_status,
        )
        db.add_all([finding_event, fieldwork_event])
        published_events.extend([finding_event, fieldwork_event])
        if linked_car is not None:
            car_event = audit_models.AuditEvent(
                amo_id=ctx.amo_id,
                entity_type="qms.car",
                entity_id=str(linked_car.id),
                action="AUTO_CREATED_FROM_FINDING",
                actor_user_id=ctx.user_id,
                after={"finding_id": str(finding.id), "car_number": linked_car.car_number},
                correlation_id=payload.client_mutation_id,
                metadata_json={
                    "module": "quality",
                    "auditId": str(audit_id),
                    "clientTimestamp": _normalise_client_timestamp(payload.client_timestamp).isoformat(),
                },
            )
            db.add(car_event)
            published_events.append(car_event)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise

    for event in published_events:
        _publish_persisted_event(event)
    return {
        "client_mutation_id": payload.client_mutation_id,
        "committed_version": committed_version,
        "replayed": False,
        **result_snapshot,
    }
