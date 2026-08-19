from __future__ import annotations

import hashlib
import hmac
import uuid
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session, selectinload

from amodb.apps.audit import models as audit_models
from amodb.apps.events.broker import EventEnvelope, publish_event
from amodb.database import get_db
from amodb.security import SECRET_KEY

from . import models
from .audit_checklist_execution_models import (
    QualityAuditChecklistExecutionEvent,
    QualityAuditChecklistExecutionGovernance,
    QualityAuditFieldworkMutationReceipt,
    QualityAuditFieldworkParticipantContribution,
)
from .audit_checklist_execution_router import (
    ChecklistExecutionUpdate,
    FieldworkMutation,
    _apply_execution_update,
    _assert_base_version,
    _canonical_from_legacy,
    _existing_receipt_or_none,
    _item,
    _locked_governance,
    _mutation_hash,
    _normalise_client_timestamp,
)
from .audit_external_access_router import _GUEST_COOKIE, _active_grant, _hash_token
from .audit_external_access_models import QualityAuditAccessGrant
from .router import public_router


router = APIRouter(prefix="/quality/audit-access", tags=["Quality / External Auditor Fieldwork"])


def _csrf_for_session(raw_token: str) -> str:
    token_hash = _hash_token(raw_token)
    return hmac.new(
        SECRET_KEY.encode("utf-8"),
        f"qms-external-fieldwork:{token_hash}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _require_csrf(raw_token: str, supplied: str | None) -> None:
    expected = _csrf_for_session(raw_token)
    if not supplied or not hmac.compare_digest(expected, supplied.strip()):
        raise HTTPException(status_code=403, detail="A valid external audit fieldwork CSRF token is required.")


def _external_auditor_grant(db: Session, raw_token: str, *, permission: str) -> QualityAuditAccessGrant:
    grant = _active_grant(db, raw_token)
    participant = grant.participant
    if participant is None or participant.participant_type != "EXTERNAL_AUDITOR" or participant.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="This audit access session is not an active external-auditor assignment.")
    scope = set(grant.scope_json or [])
    if permission not in scope:
        raise HTTPException(status_code=403, detail=f"This external audit assignment does not permit {permission}.")
    if participant.audit_id != grant.audit_id:
        raise HTTPException(status_code=403, detail="External auditor assignment does not match this audit grant.")
    return grant


def _latest_contributions(
    db: Session,
    *,
    amo_id: str,
    audit_id: uuid.UUID,
    participant_id: str,
) -> dict[uuid.UUID, QualityAuditFieldworkParticipantContribution]:
    rows = db.query(QualityAuditFieldworkParticipantContribution).filter(
        QualityAuditFieldworkParticipantContribution.amo_id == amo_id,
        QualityAuditFieldworkParticipantContribution.audit_id == audit_id,
        QualityAuditFieldworkParticipantContribution.participant_id == participant_id,
    ).order_by(QualityAuditFieldworkParticipantContribution.created_at.asc()).all()
    latest: dict[uuid.UUID, QualityAuditFieldworkParticipantContribution] = {}
    for row in rows:
        latest[row.checklist_item_id] = row
    return latest


def _external_item_dict(
    item: models.QualityAuditChecklistItem,
    governance: QualityAuditChecklistExecutionGovernance | None,
    contribution: QualityAuditFieldworkParticipantContribution | None,
) -> dict[str, Any]:
    return {
        "checklist_item_id": str(item.id),
        "section": item.section,
        "checklist_ref": item.checklist_ref,
        "requirement_ref": item.requirement_ref,
        "prompt": item.prompt,
        "canonical_response_status": governance.canonical_response_status if governance else _canonical_from_legacy(item.response_status),
        "entity_version": int(governance.entity_version or 1) if governance else 0,
        "finding_id": str(item.finding_id) if item.finding_id else None,
        "my_auditor_notes": contribution.auditor_notes if contribution else None,
        "my_evidence_references": list(contribution.evidence_references or []) if contribution else [],
        "my_last_contribution_at": contribution.created_at.isoformat() if contribution and contribution.created_at else None,
        "updated_at": governance.updated_at.isoformat() if governance and governance.updated_at else (item.updated_at.isoformat() if item.updated_at else None),
    }


def _publish(row: audit_models.AuditEvent) -> None:
    try:
        occurred = row.occurred_at or row.created_at
        publish_event(EventEnvelope(
            id=str(row.id),
            type=f"{row.entity_type}.{row.action}".lower(),
            entityType=row.entity_type,
            entityId=row.entity_id,
            action=row.action,
            timestamp=occurred.isoformat() if occurred else "",
            actor=None,
            metadata={"amoId": row.amo_id, **(row.metadata_json or {})},
        ))
    except Exception:
        # The durable audit_events row remains the reconnect/replay source.
        return


@router.get("/fieldwork")
def get_external_auditor_fieldwork(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _external_auditor_grant(db, amo_qms_audit_guest, permission="audit:read_assigned")
    participant = grant.participant
    scope = set(grant.scope_json or [])
    items = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == grant.amo_id,
        models.QualityAuditChecklistItem.audit_id == grant.audit_id,
    ).order_by(models.QualityAuditChecklistItem.section.asc(), models.QualityAuditChecklistItem.sort_order.asc()).limit(1000).all()
    governance_rows = db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == grant.amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == grant.audit_id,
    ).all()
    by_item = {row.checklist_item_id: row for row in governance_rows}
    contributions = _latest_contributions(
        db,
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        participant_id=participant.id,
    )
    can_draft_findings = "audit:finding_draft" in scope
    return {
        "audit_id": str(grant.audit_id),
        "participant_id": participant.id,
        "csrf_token": _csrf_for_session(amo_qms_audit_guest),
        "can_execute_checklist": "audit:checklist_execute" in scope,
        "can_draft_findings": can_draft_findings,
        "finding_draft_blocker": None if can_draft_findings else "This external audit assignment does not permit finding drafts.",
        "items": [
            _external_item_dict(item, by_item.get(item.id), contributions.get(item.id))
            for item in items
        ],
    }


@router.post("/fieldwork/checklist-items/{item_id}/mutations")
def mutate_external_auditor_checklist(
    item_id: uuid.UUID,
    payload: FieldworkMutation,
    x_qms_csrf: str | None = Header(default=None, alias="X-QMS-CSRF"),
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    _require_csrf(amo_qms_audit_guest, x_qms_csrf)
    grant = _external_auditor_grant(db, amo_qms_audit_guest, permission="audit:checklist_execute")
    participant = grant.participant

    if payload.canonical_response_status in {"NONCOMPLIANT", "OBSERVATION"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EXTERNAL_FINDING_DRAFT_REQUIRED",
                "message": "External auditors must use the governed finding-draft workflow for non-compliance or observations; formal promotion remains a Quality-owned action.",
            },
        )

    actor_ctx = SimpleNamespace(amo_id=grant.amo_id, user_id=None)
    payload_hash = _mutation_hash(payload)
    existing = _existing_receipt_or_none(
        db,
        ctx=actor_ctx,
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

    item = _item(db, amo_id=grant.amo_id, audit_id=grant.audit_id, item_id=item_id, lock=True)
    governance = _locked_governance(db, ctx=actor_ctx, audit_id=grant.audit_id, item_id=item_id)
    current_version = _assert_base_version(
        payload_base_version=payload.base_version,
        client_mutation_id=payload.client_mutation_id,
        item=item,
        governance=governance,
    )

    # External contributions must never replace internal Quality notes/evidence.
    central_notes = governance.auditor_notes if governance else None
    central_evidence = list(governance.evidence_references or []) if governance else []
    before_new = set(db.new)
    governance = _apply_execution_update(
        db,
        ctx=actor_ctx,
        item=item,
        payload=ChecklistExecutionUpdate(
            canonical_response_status=payload.canonical_response_status,
            auditor_notes=central_notes,
            evidence_references=central_evidence,
            reason=f"External auditor participant {participant.id} checklist execution: {payload.reason}",
        ),
        governance=governance,
    )
    governance.updated_by_participant_id = participant.id
    governance.updated_by_user_id = None

    execution_event = next(
        (
            obj for obj in db.new
            if obj not in before_new
            and isinstance(obj, QualityAuditChecklistExecutionEvent)
            and obj.checklist_item_id == item_id
        ),
        None,
    )
    if execution_event is not None:
        execution_event.actor_user_id = None
        execution_event.actor_participant_id = participant.id
        execution_event.after_snapshot = {
            **dict(execution_event.after_snapshot or {}),
            "actor_participant_id": participant.id,
        }

    contribution = QualityAuditFieldworkParticipantContribution(
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        checklist_item_id=item_id,
        participant_id=participant.id,
        client_mutation_id=payload.client_mutation_id,
        canonical_response_status=payload.canonical_response_status,
        auditor_notes=payload.auditor_notes.strip() if payload.auditor_notes else None,
        evidence_references=list(payload.evidence_references or []),
    )
    db.add(contribution)
    committed_version = int(governance.entity_version or 1)
    db.flush()
    external_row = _external_item_dict(item, governance, contribution)

    db.add(QualityAuditFieldworkMutationReceipt(
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        checklist_item_id=item_id,
        client_mutation_id=payload.client_mutation_id,
        device_id=payload.device_id,
        device_sequence=payload.device_sequence,
        client_timestamp=_normalise_client_timestamp(payload.client_timestamp),
        base_version=payload.base_version,
        committed_version=committed_version,
        operation=payload.operation,
        payload_hash=payload_hash,
        result_snapshot=external_row,
        actor_user_id=None,
        actor_participant_id=participant.id,
    ))
    event = audit_models.AuditEvent(
        amo_id=grant.amo_id,
        entity_type="qms.audit.checklist_item",
        entity_id=str(item_id),
        action="UPDATED_BY_EXTERNAL_AUDITOR",
        actor_user_id=None,
        before={"entity_version": current_version},
        after={"entity_version": committed_version, "canonical_response_status": payload.canonical_response_status},
        correlation_id=payload.client_mutation_id,
        metadata_json={
            "module": "quality",
            "auditId": str(grant.audit_id),
            "checklistItemId": str(item_id),
            "externalParticipantId": participant.id,
            "clientMutationId": payload.client_mutation_id,
            "deviceId": payload.device_id,
            "deviceSequence": payload.device_sequence,
            "clientTimestamp": _normalise_client_timestamp(payload.client_timestamp).isoformat(),
            "entityVersion": committed_version,
        },
    )
    db.add(event)
    db.flush()
    db.commit()
    _publish(event)
    return {
        "client_mutation_id": payload.client_mutation_id,
        "committed_version": committed_version,
        "replayed": False,
        "row": jsonable_encoder(external_row),
    }


# This module is imported after the base external-access routes. Insert its
# purpose-bound auditor routes ahead of the public router's generic handlers.
public_router.routes[0:0] = list(router.routes)
