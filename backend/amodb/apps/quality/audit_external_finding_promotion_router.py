from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.database import get_write_db

from .audit_checklist_execution_models import QualityAuditChecklistExecutionGovernance
from .audit_external_finding_draft_router import _add_event, _audit_event, _draft_dict, _load_draft, _publish, _status
from .audit_official_finding_service import create_official_finding_transaction
from .enums import FindingLevel, QMSFindingSeverity
from .tenant_security import TenantContext, assert_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality external finding draft promotion"])


class DraftPromotion(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)
    review_note: str | None = Field(default=None, max_length=12000)


@router.post(
    "/audits/{audit_id}/external-finding-drafts/{draft_id}/promote",
    name="promote_external_finding_draft",
)
def promote_external_finding_draft(
    audit_id: uuid.UUID,
    draft_id: str,
    payload: DraftPromotion,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Promote one submitted external proposal into the authoritative finding engine.

    No official record is created by the external participant. The internal
    Quality reviewer owns the formal finding transaction; the originating
    participant/draft remain retained as source metadata and append-only draft
    lifecycle evidence.
    """

    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _load_draft(db, amo_id=ctx.amo_id, audit_id=audit_id, draft_id=draft_id)
    if _status(row) != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Only a submitted external finding draft may be promoted.")

    governance = db.query(QualityAuditChecklistExecutionGovernance).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == ctx.amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
        QualityAuditChecklistExecutionGovernance.checklist_item_id == row.checklist_item_id,
    ).first()
    central_notes = governance.auditor_notes if governance else None
    central_evidence = list(governance.evidence_references or []) if governance else []
    canonical_response = "OBSERVATION" if row.draft_type == "OBSERVATION" else "NONCOMPLIANT"
    correlation_id = f"external-draft-promotion:{row.id}"

    try:
        result = create_official_finding_transaction(
            db,
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            checklist_item_id=row.checklist_item_id,
            actor_user_id=ctx.user_id,
            canonical_response_status=canonical_response,
            severity=QMSFindingSeverity(row.proposed_severity),
            level=FindingLevel(row.proposed_level),
            requirement_ref=row.requirement_ref,
            description=row.description,
            objective_evidence=row.objective_evidence,
            safety_sensitive=False,
            target_close_date=None,
            execution_auditor_notes=central_notes,
            execution_evidence_references=central_evidence,
            execution_reason=f"Quality promoted external finding draft {row.id}: {payload.reason}",
            correlation_id=correlation_id,
            source_metadata={
                "externalDraftId": row.id,
                "externalParticipantId": row.participant_id,
                "externalClientMutationId": row.client_mutation_id,
            },
        )
        _add_event(
            db,
            row=row,
            event_type="PROMOTED",
            reason=payload.reason,
            review_note=payload.review_note,
            actor_user_id=ctx.user_id,
            promoted_finding_id=result.finding.id,
        )
        draft_event = _audit_event(
            row=row,
            action="PROMOTED",
            actor_user_id=ctx.user_id,
            actor_participant_id=None,
        )
        draft_event.after = {
            **dict(draft_event.after or {}),
            "promoted_finding_id": str(result.finding.id),
            "external_participant_id": row.participant_id,
        }
        db.add(draft_event)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise

    for event in [*result.events, draft_event]:
        _publish(event)
    loaded = _load_draft(db, amo_id=ctx.amo_id, audit_id=audit_id, draft_id=draft_id)
    return {
        "draft": _draft_dict(loaded),
        "finding": result.finding_snapshot,
        "checklist": result.row_snapshot,
        "car_id": str(result.car.id) if result.car is not None else None,
    }
