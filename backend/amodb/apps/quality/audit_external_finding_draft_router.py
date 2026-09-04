from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.apps.audit import models as audit_models
from amodb.apps.events.broker import EventEnvelope, publish_event
from amodb.database import get_db, get_read_db, get_write_db

from . import models
from .audit_external_access_router import _GUEST_COOKIE
from .audit_external_fieldwork_router import _external_auditor_grant, _require_csrf
from .audit_checklist_execution_router import _internal_fieldwork_viewer, _mark_fieldwork_started, _require_fieldwork_write_window
from .audit_external_access_router import _audit_for_tenant
from .audit_external_finding_draft_models import QualityAuditExternalFindingDraft, QualityAuditExternalFindingDraftEvent
from .enums import FindingLevel, QMSFindingSeverity, QMSFindingType
from .router import public_router
from .service import normalize_finding_level
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


public_draft_router = APIRouter(prefix="/quality/audit-access", tags=["Quality / External Finding Drafts"])
router = APIRouter(tags=["Quality external finding draft review"])

DraftEventType = Literal["CREATED", "SUBMITTED", "RETURNED", "PROMOTED", "WITHDRAWN"]


class ExternalFindingDraftCreate(BaseModel):
    client_mutation_id: str = Field(min_length=8, max_length=128)
    device_id: str = Field(min_length=8, max_length=128)
    device_sequence: int = Field(ge=0)
    client_timestamp: datetime
    draft_type: Literal["NON_CONFORMITY", "OBSERVATION"]
    proposed_severity: QMSFindingSeverity
    proposed_level: FindingLevel
    requirement_ref: str | None = Field(default=None, max_length=255)
    description: str = Field(min_length=8, max_length=12000)
    objective_evidence: str | None = Field(default=None, max_length=12000)
    evidence_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    supersedes_draft_id: str | None = Field(default=None, max_length=36)


class DraftTransition(BaseModel):
    reason: str = Field(min_length=4, max_length=4000)
    review_note: str | None = Field(default=None, max_length=12000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_timestamp(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _draft_hash(payload: ExternalFindingDraftCreate) -> str:
    encoded = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _status(row: QualityAuditExternalFindingDraft) -> str:
    return row.events[-1].event_type if row.events else "CREATED"


def _event_dict(event: QualityAuditExternalFindingDraftEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "reason": event.reason,
        "review_note": event.review_note,
        "actor_user_id": event.actor_user_id,
        "actor_participant_id": event.actor_participant_id,
        "promoted_finding_id": str(event.promoted_finding_id) if event.promoted_finding_id else None,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _draft_dict(row: QualityAuditExternalFindingDraft) -> dict[str, Any]:
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "checklist_item_id": str(row.checklist_item_id),
        "participant_id": row.participant_id,
        "client_mutation_id": row.client_mutation_id,
        "client_timestamp": row.client_timestamp.isoformat() if row.client_timestamp else None,
        "draft_type": row.draft_type,
        "proposed_severity": row.proposed_severity,
        "proposed_level": row.proposed_level,
        "requirement_ref": row.requirement_ref,
        "description": row.description,
        "objective_evidence": row.objective_evidence,
        "evidence_references": list(row.evidence_references or []),
        "supersedes_draft_id": row.supersedes_draft_id,
        "status": _status(row),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "events": [_event_dict(event) for event in list(row.events or [])],
    }


def _add_event(
    db: Session,
    *,
    row: QualityAuditExternalFindingDraft,
    event_type: DraftEventType,
    reason: str,
    review_note: str | None = None,
    actor_user_id: str | None = None,
    actor_participant_id: str | None = None,
    promoted_finding_id: uuid.UUID | None = None,
) -> QualityAuditExternalFindingDraftEvent:
    event = QualityAuditExternalFindingDraftEvent(
        amo_id=row.amo_id,
        audit_id=row.audit_id,
        draft_id=row.id,
        event_type=event_type,
        reason=reason.strip(),
        review_note=review_note.strip() if review_note else None,
        actor_user_id=actor_user_id,
        actor_participant_id=actor_participant_id,
        promoted_finding_id=promoted_finding_id,
    )
    db.add(event)
    return event


def _audit_event(
    *,
    row: QualityAuditExternalFindingDraft,
    action: str,
    actor_user_id: str | None,
    actor_participant_id: str | None,
) -> audit_models.AuditEvent:
    return audit_models.AuditEvent(
        amo_id=row.amo_id,
        entity_type="qms.external_finding_draft",
        entity_id=row.id,
        action=action,
        actor_user_id=actor_user_id,
        after={
            "audit_id": str(row.audit_id),
            "checklist_item_id": str(row.checklist_item_id),
            "status": action,
            "draft_type": row.draft_type,
            "proposed_level": row.proposed_level,
        },
        correlation_id=row.client_mutation_id,
        metadata_json={
            "module": "quality",
            "auditId": str(row.audit_id),
            "checklistItemId": str(row.checklist_item_id),
            "externalParticipantId": actor_participant_id,
        },
    )


def _publish(event: audit_models.AuditEvent) -> None:
    try:
        occurred = event.occurred_at or event.created_at
        publish_event(EventEnvelope(
            id=str(event.id),
            type=f"{event.entity_type}.{event.action}".lower(),
            entityType=event.entity_type,
            entityId=event.entity_id,
            action=event.action,
            timestamp=occurred.isoformat() if occurred else "",
            actor={"userId": event.actor_user_id} if event.actor_user_id else None,
            metadata={"amoId": event.amo_id, **(event.metadata_json or {})},
        ))
    except Exception:
        return


def _load_draft(db: Session, *, amo_id: str, audit_id: uuid.UUID, draft_id: str, participant_id: str | None = None) -> QualityAuditExternalFindingDraft:
    query = db.query(QualityAuditExternalFindingDraft).options(selectinload(QualityAuditExternalFindingDraft.events)).filter(
        QualityAuditExternalFindingDraft.amo_id == amo_id,
        QualityAuditExternalFindingDraft.audit_id == audit_id,
        QualityAuditExternalFindingDraft.id == draft_id,
    )
    if participant_id is not None:
        query = query.filter(QualityAuditExternalFindingDraft.participant_id == participant_id)
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="External finding draft not found.")
    return row


def _assert_classification(payload: ExternalFindingDraftCreate) -> None:
    requested_type = QMSFindingType.OBSERVATION if payload.draft_type == "OBSERVATION" else QMSFindingType.NON_CONFORMITY
    normalized = normalize_finding_level(payload.proposed_severity, payload.proposed_level, requested_type)
    if payload.draft_type == "OBSERVATION" and normalized != FindingLevel.LEVEL_4:
        raise HTTPException(status_code=422, detail="Observation drafts must use the governed Level 4 classification.")
    if payload.draft_type == "NON_CONFORMITY" and normalized == FindingLevel.LEVEL_4:
        raise HTTPException(status_code=422, detail="Non-conformity drafts must use governed Level 1, 2 or 3 classification.")


@public_draft_router.get("/finding-drafts")
def list_my_external_finding_drafts(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _external_auditor_grant(db, amo_qms_audit_guest, permission="audit:finding_draft")
    participant = grant.participant
    rows = db.query(QualityAuditExternalFindingDraft).options(selectinload(QualityAuditExternalFindingDraft.events)).filter(
        QualityAuditExternalFindingDraft.amo_id == grant.amo_id,
        QualityAuditExternalFindingDraft.audit_id == grant.audit_id,
        QualityAuditExternalFindingDraft.participant_id == participant.id,
    ).order_by(QualityAuditExternalFindingDraft.created_at.desc()).limit(200).all()
    return {"items": [_draft_dict(row) for row in rows]}


@public_draft_router.post("/fieldwork/checklist-items/{item_id}/finding-drafts")
def create_external_finding_draft(
    item_id: uuid.UUID,
    payload: ExternalFindingDraftCreate,
    x_qms_csrf: str | None = Header(default=None, alias="X-QMS-CSRF"),
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    _require_csrf(amo_qms_audit_guest, x_qms_csrf)
    grant = _external_auditor_grant(db, amo_qms_audit_guest, permission="audit:finding_draft")
    participant = grant.participant
    audit = _audit_for_tenant(db, amo_id=grant.amo_id, audit_id=grant.audit_id)
    _require_fieldwork_write_window(db, amo_id=grant.amo_id, audit=audit)
    _mark_fieldwork_started(audit)
    _assert_classification(payload)

    item = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == grant.amo_id,
        models.QualityAuditChecklistItem.audit_id == grant.audit_id,
        models.QualityAuditChecklistItem.id == item_id,
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Assigned checklist item not found.")
    if item.finding_id is not None:
        raise HTTPException(status_code=409, detail="This checklist item already has a governed finding.")

    payload_hash = _draft_hash(payload)
    existing = db.query(QualityAuditExternalFindingDraft).options(selectinload(QualityAuditExternalFindingDraft.events)).filter(
        QualityAuditExternalFindingDraft.amo_id == grant.amo_id,
        QualityAuditExternalFindingDraft.client_mutation_id == payload.client_mutation_id,
    ).first()
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise HTTPException(status_code=409, detail="This external finding draft mutation id was already used with different content.")
        return _draft_dict(existing)

    if payload.supersedes_draft_id:
        prior = _load_draft(
            db,
            amo_id=grant.amo_id,
            audit_id=grant.audit_id,
            draft_id=payload.supersedes_draft_id,
            participant_id=participant.id,
        )
        if _status(prior) != "RETURNED":
            raise HTTPException(status_code=409, detail="Only a returned draft may be superseded by a revised draft.")
        if prior.checklist_item_id != item_id:
            raise HTTPException(status_code=409, detail="A revised draft must remain linked to the same checklist item.")

    row = QualityAuditExternalFindingDraft(
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        checklist_item_id=item_id,
        participant_id=participant.id,
        client_mutation_id=payload.client_mutation_id,
        device_id=payload.device_id,
        device_sequence=payload.device_sequence,
        client_timestamp=_normalise_timestamp(payload.client_timestamp),
        payload_hash=payload_hash,
        draft_type=payload.draft_type,
        proposed_severity=payload.proposed_severity.value,
        proposed_level=payload.proposed_level.value,
        requirement_ref=payload.requirement_ref.strip() if payload.requirement_ref else None,
        description=payload.description.strip(),
        objective_evidence=payload.objective_evidence.strip() if payload.objective_evidence else None,
        evidence_references=list(payload.evidence_references),
        supersedes_draft_id=payload.supersedes_draft_id,
    )
    db.add(row)
    db.flush()
    _add_event(db, row=row, event_type="CREATED", reason="External auditor finding draft created.", actor_participant_id=participant.id)
    audit_event = _audit_event(row=row, action="CREATED", actor_user_id=None, actor_participant_id=participant.id)
    db.add(audit_event)
    db.flush()
    db.commit()
    loaded = _load_draft(db, amo_id=grant.amo_id, audit_id=grant.audit_id, draft_id=row.id, participant_id=participant.id)
    _publish(audit_event)
    return _draft_dict(loaded)


@public_draft_router.post("/finding-drafts/{draft_id}/submit")
def submit_external_finding_draft(
    draft_id: str,
    payload: DraftTransition,
    x_qms_csrf: str | None = Header(default=None, alias="X-QMS-CSRF"),
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    _require_csrf(amo_qms_audit_guest, x_qms_csrf)
    grant = _external_auditor_grant(db, amo_qms_audit_guest, permission="audit:finding_draft")
    participant = grant.participant
    audit = _audit_for_tenant(db, amo_id=grant.amo_id, audit_id=grant.audit_id)
    _require_fieldwork_write_window(db, amo_id=grant.amo_id, audit=audit)
    row = _load_draft(db, amo_id=grant.amo_id, audit_id=grant.audit_id, draft_id=draft_id, participant_id=participant.id)
    if _status(row) != "CREATED":
        raise HTTPException(status_code=409, detail="Only a newly created draft revision may be submitted to Quality.")
    _add_event(db, row=row, event_type="SUBMITTED", reason=payload.reason, actor_participant_id=participant.id)
    event = _audit_event(row=row, action="SUBMITTED", actor_user_id=None, actor_participant_id=participant.id)
    db.add(event)
    db.flush()
    db.commit()
    loaded = _load_draft(db, amo_id=grant.amo_id, audit_id=grant.audit_id, draft_id=draft_id, participant_id=participant.id)
    _publish(event)
    return _draft_dict(loaded)


@public_draft_router.post("/finding-drafts/{draft_id}/withdraw")
def withdraw_external_finding_draft(
    draft_id: str,
    payload: DraftTransition,
    x_qms_csrf: str | None = Header(default=None, alias="X-QMS-CSRF"),
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    _require_csrf(amo_qms_audit_guest, x_qms_csrf)
    grant = _external_auditor_grant(db, amo_qms_audit_guest, permission="audit:finding_draft")
    participant = grant.participant
    row = _load_draft(db, amo_id=grant.amo_id, audit_id=grant.audit_id, draft_id=draft_id, participant_id=participant.id)
    if _status(row) not in {"CREATED", "SUBMITTED", "RETURNED"}:
        raise HTTPException(status_code=409, detail="This draft can no longer be withdrawn.")
    _add_event(db, row=row, event_type="WITHDRAWN", reason=payload.reason, actor_participant_id=participant.id)
    event = _audit_event(row=row, action="WITHDRAWN", actor_user_id=None, actor_participant_id=participant.id)
    db.add(event)
    db.flush()
    db.commit()
    loaded = _load_draft(db, amo_id=grant.amo_id, audit_id=grant.audit_id, draft_id=draft_id, participant_id=participant.id)
    _publish(event)
    return _draft_dict(loaded)


@router.get("/audits/{audit_id}/external-finding-drafts")
def list_external_finding_drafts_for_quality(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _internal_fieldwork_viewer(db, ctx=ctx, audit_id=audit_id)
    rows = db.query(QualityAuditExternalFindingDraft).options(selectinload(QualityAuditExternalFindingDraft.events)).filter(
        QualityAuditExternalFindingDraft.amo_id == ctx.amo_id,
        QualityAuditExternalFindingDraft.audit_id == audit_id,
    ).order_by(QualityAuditExternalFindingDraft.created_at.desc()).limit(500).all()
    return {"items": [_draft_dict(row) for row in rows]}


@router.post("/audits/{audit_id}/external-finding-drafts/{draft_id}/return")
def return_external_finding_draft(
    audit_id: uuid.UUID,
    draft_id: str,
    payload: DraftTransition,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _load_draft(db, amo_id=ctx.amo_id, audit_id=audit_id, draft_id=draft_id)
    if _status(row) != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Only a submitted external finding draft may be returned.")
    _add_event(
        db,
        row=row,
        event_type="RETURNED",
        reason=payload.reason,
        review_note=payload.review_note,
        actor_user_id=ctx.user_id,
    )
    event = _audit_event(row=row, action="RETURNED", actor_user_id=ctx.user_id, actor_participant_id=None)
    db.add(event)
    db.flush()
    db.commit()
    loaded = _load_draft(db, amo_id=ctx.amo_id, audit_id=audit_id, draft_id=draft_id)
    _publish(event)
    return _draft_dict(loaded)


# Public routes are purpose-bound to the existing HTTP-only external audit session.
public_router.routes[0:0] = list(public_draft_router.routes)
