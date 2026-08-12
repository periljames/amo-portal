from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_decision_policy import require_decision_approver
from .workspace_evidence_router import validate_evidence_references
from .workspace_router import _authority_payload, _event
from .workspace_service import (
    audit,
    get_manual,
    get_revision,
    get_workflow,
    require_control_user,
    resolve_tenant,
    utcnow,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Authority"])

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"SUBMITTED", "WITHDRAWN"},
    "SUBMITTED": {"IN_REVIEW", "QUERY_RECEIVED", "APPROVED", "REJECTED", "WITHDRAWN"},
    "IN_REVIEW": {"QUERY_RECEIVED", "APPROVED", "REJECTED", "WITHDRAWN"},
    "QUERY_RECEIVED": {"SUBMITTED", "IN_REVIEW", "APPROVED", "REJECTED", "WITHDRAWN"},
    "APPROVED": set(),
    "REJECTED": set(),
    "WITHDRAWN": set(),
}


def _merge_asset_evidence(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for item in [*existing, *incoming]:
        asset_id = str((item or {}).get("asset_id") or "").strip()
        if not asset_id or asset_id in seen:
            continue
        seen.add(asset_id)
        merged.append(dict(item))
    return merged


def validate_authority_update(
    row: dm.DocumentAuthoritySubmission,
    payload: schemas.AuthoritySubmissionUpdate,
) -> None:
    if payload.status != row.status:
        allowed = _ALLOWED_TRANSITIONS.get(row.status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "AUTHORITY_TRANSITION_INVALID",
                    "message": f"Authority submission cannot move from {row.status} to {payload.status}.",
                    "allowed_statuses": sorted(allowed),
                },
            )

    resulting_evidence = (
        list(payload.evidence)
        if payload.evidence is not None
        else list(row.evidence_json or [])
    )
    raw_response_summary = (
        payload.response_summary
        if "response_summary" in payload.model_fields_set
        else row.response_summary
    )
    response_summary = str(raw_response_summary or "").strip()

    if payload.status == "SUBMITTED" and not resulting_evidence:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "AUTHORITY_SUBMISSION_EVIDENCE_REQUIRED",
                "message": "Submission evidence is required before authority status can be marked submitted.",
            },
        )
    if payload.status == "QUERY_RECEIVED" and not response_summary:
        raise HTTPException(
            status_code=409,
            detail="The authority query or response summary must be recorded",
        )
    if payload.status == "APPROVED":
        if not resulting_evidence:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "AUTHORITY_APPROVAL_EVIDENCE_REQUIRED",
                    "message": "Authority approval evidence is required before approval can be recorded.",
                },
            )
        if not response_summary:
            raise HTTPException(
                status_code=409,
                detail="The authority approval reference or response summary must be recorded",
            )
    if payload.status in {"REJECTED", "WITHDRAWN"} and not response_summary:
        raise HTTPException(
            status_code=409,
            detail=f"A reason is required when an authority submission is {payload.status.lower()}",
        )


@router.post(
    "/t/{tenant_slug}/authority-submissions",
    include_in_schema=False,
)
def create_authority_submission_with_evidence_guards(
    tenant_slug: str,
    payload: schemas.AuthoritySubmissionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    revision = get_revision(db, manual, payload.revision_id)
    workflow = get_workflow(db, tenant, revision.id)
    if payload.workflow_id and (not workflow or workflow.id != payload.workflow_id):
        raise HTTPException(status_code=400, detail="Workflow does not match the revision")
    evidence = validate_evidence_references(
        db,
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        evidence=list(payload.evidence or []),
    )
    row = dm.DocumentAuthoritySubmission(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        workflow_id=payload.workflow_id or (workflow.id if workflow else None),
        authority_name=payload.authority_name.strip(),
        submission_reference=payload.submission_reference.strip(),
        status="DRAFT",
        response_due_at=payload.response_due_at,
        evidence_json=evidence,
    )
    db.add(row)
    db.flush()
    audit(
        db,
        tenant,
        request,
        "document.authority.created",
        "document_authority_submission",
        row.id,
        _authority_payload(row),
    )
    db.commit()
    return _authority_payload(row)


@router.patch(
    "/t/{tenant_slug}/authority-submissions/{submission_id}",
    include_in_schema=False,
)
def update_authority_submission_with_guards(
    tenant_slug: str,
    submission_id: str,
    payload: schemas.AuthoritySubmissionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Update authority evidence without silently advancing the document workflow."""
    require_decision_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = (
        db.query(dm.DocumentAuthoritySubmission)
        .filter(
            dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id,
            dm.DocumentAuthoritySubmission.id == submission_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Authority submission not found")

    existing_evidence = validate_evidence_references(
        db,
        tenant_id=tenant.amo_id,
        manual_id=row.manual_id,
        evidence=list(row.evidence_json or []),
    ) if row.evidence_json else []
    normalized_evidence = None
    if payload.evidence is not None:
        incoming = validate_evidence_references(
            db,
            tenant_id=tenant.amo_id,
            manual_id=row.manual_id,
            evidence=list(payload.evidence),
        )
        if row.status == "DRAFT" and payload.status == "DRAFT":
            normalized_evidence = incoming
        else:
            normalized_evidence = _merge_asset_evidence(existing_evidence, incoming)
    elif payload.status in {"SUBMITTED", "APPROVED"}:
        normalized_evidence = existing_evidence

    if normalized_evidence is not None:
        payload = payload.model_copy(update={"evidence": normalized_evidence})

    validate_authority_update(row, payload)
    before = _authority_payload(row)
    row.status = payload.status
    if "response_summary" in payload.model_fields_set:
        row.response_summary = payload.response_summary
    if "response_due_at" in payload.model_fields_set:
        row.response_due_at = payload.response_due_at
    if normalized_evidence is not None:
        row.evidence_json = normalized_evidence
    if payload.status == "SUBMITTED":
        row.submitted_at = row.submitted_at or utcnow()
        row.submitted_by_user_id = row.submitted_by_user_id or current_user.id
    if payload.status == "APPROVED":
        row.approved_at = row.approved_at or utcnow()
    row.updated_at = utcnow()
    after = _authority_payload(row)
    audit(
        db,
        tenant,
        request,
        "document.authority.updated",
        "document_authority_submission",
        row.id,
        {"before": before, "after": after},
    )
    db.commit()
    _event(
        event_type="doc_control.authority_updated",
        entity_type="document_authority_submission",
        entity_id=row.id,
        action=row.status.lower(),
        user=current_user,
        tenant_id=tenant.amo_id,
        metadata={"manual_id": row.manual_id, "revision_id": row.revision_id},
    )
    return after
