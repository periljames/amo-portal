from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import governance_models as gm
from . import knowledge_models as km
from .governance_backfill import create_run, process_batch, serialize_run
from .governance_schemas import (
    AnnotationCreate,
    BackfillRequest,
    BackfillResumeRequest,
    GovernanceDecision,
    LocationInput,
    RelationshipCreate,
    ResponsibilityCreate,
)
from .governance_service import (
    ASSIGNMENT_SOURCES,
    CONFIRMATION_STATES,
    RELATIONSHIP_SOURCES,
    RELATIONSHIP_TYPES,
    RESPONSIBILITY_TYPES,
    document_governance_payload,
    governance_dashboard,
    governance_library,
    incoming_would_replace_confirmed,
    serialize_assignment,
    serialize_relationship,
    validate_assignment_target,
)
from .workspace_service import (
    get_manual,
    get_profile,
    get_revision,
    is_control_user,
    require_control_user,
    require_manual_access,
    resolve_tenant,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Governance"])


def utcnow() -> datetime:
    return datetime.utcnow()


def _audit(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    user: account_models.User,
    request: Request,
    action: str,
    entity_type: str,
    entity_id: str,
    diff: dict[str, Any],
) -> None:
    db.add(manual_models.ManualAuditLog(
        tenant_id=tenant.id,
        actor_id=user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_device=f"{request.client.host if request.client else 'unknown'}::{request.headers.get('user-agent', 'n/a')}",
        diff_json=diff,
    ))


def _validate_assignee_tenant(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    payload: ResponsibilityCreate,
) -> None:
    if payload.assignee_user_id:
        exists = db.query(account_models.User.id).filter(
            account_models.User.id == payload.assignee_user_id,
            account_models.User.amo_id == tenant.amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        ).first()
        if not exists:
            raise HTTPException(status_code=422, detail="The selected responsible person is not an active user in this tenant")
    if payload.assignee_department_id:
        exists = db.query(account_models.Department.id).filter(
            account_models.Department.id == payload.assignee_department_id,
            account_models.Department.amo_id == tenant.amo_id,
            account_models.Department.is_active.is_(True),
        ).first()
        if not exists:
            raise HTTPException(status_code=422, detail="The selected department is not active in this tenant")
    if payload.assignee_org_unit_id:
        from amodb.apps.workforce.governance_models import WorkforceOrgUnit

        exists = db.query(WorkforceOrgUnit.id).filter(
            WorkforceOrgUnit.id == payload.assignee_org_unit_id,
            WorkforceOrgUnit.amo_id == tenant.amo_id,
            WorkforceOrgUnit.is_active.is_(True),
        ).first()
        if not exists:
            raise HTTPException(status_code=422, detail="The selected organization unit is not active in this tenant")


def _location(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    manual: manual_models.Manual,
    revision: manual_models.ManualRevision,
    payload: LocationInput,
) -> gm.DocumentLocation:
    if not revision.source_sha256:
        raise HTTPException(status_code=409, detail="The source revision has no authoritative checksum")
    existing = db.query(gm.DocumentLocation).filter(
        gm.DocumentLocation.tenant_id == tenant.amo_id,
        gm.DocumentLocation.revision_id == revision.id,
        gm.DocumentLocation.location_key == payload.location_key,
    ).first()
    if existing:
        if existing.source_sha256 != revision.source_sha256:
            raise HTTPException(status_code=409, detail="The saved location belongs to a different immutable source checksum")
        return existing
    row = gm.DocumentLocation(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        source_sha256=revision.source_sha256,
        location_key=payload.location_key,
        location_type=payload.location_type,
        page_number=payload.page_number,
        normalized_rects_json=list(payload.normalized_rects),
        exact_quote=payload.exact_quote,
        prefix_context=payload.prefix_context,
        suffix_context=payload.suffix_context,
        section_id=payload.section_id,
        block_id=payload.block_id,
        char_start=payload.char_start,
        char_end=payload.char_end,
        sheet_name=payload.sheet_name,
        cell_range=payload.cell_range,
        slide_number=payload.slide_number,
        object_id=payload.object_id,
        image_region_json=dict(payload.image_region),
        adapter_name=payload.adapter_name,
        adapter_version=payload.adapter_version,
    )
    db.add(row)
    db.flush()
    return row


@router.get("/t/{tenant_slug}/governance/dashboard")
def get_governance_dashboard(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    return {**governance_dashboard(db, tenant=tenant), "capabilities": {"control": True}}


@router.get("/t/{tenant_slug}/governance/library")
def get_governance_library(
    tenant_slug: str,
    q: str | None = None,
    document_type: str | None = None,
    lifecycle_status: str | None = None,
    control_status: str | None = None,
    owner_user_id: str | None = None,
    department_id: str | None = None,
    indexing_status: str | None = None,
    unresolved_ownership: bool = False,
    unresolved_relationships: bool = False,
    superseded: bool | None = None,
    sort: str = "code",
    direction: str = "asc",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=250),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    return governance_library(
        db,
        tenant=tenant,
        current_user=current_user,
        q=q,
        document_type=document_type,
        lifecycle_status=lifecycle_status,
        control_status=control_status,
        owner_user_id=owner_user_id,
        department_id=department_id,
        indexing_status=indexing_status,
        unresolved_ownership=unresolved_ownership,
        unresolved_relationships=unresolved_relationships,
        superseded=superseded,
        sort=sort,
        direction=direction,
        page=page,
        per_page=per_page,
    )


@router.get("/t/{tenant_slug}/documents/{manual_id}/governance")
def get_document_governance(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    payload = document_governance_payload(db, tenant=tenant, manual=manual, current_user=current_user)
    payload["capabilities"] = {
        "control": is_control_user(current_user),
        "annotate": True,
        "controlled_evidence": is_control_user(current_user),
    }
    return payload


@router.post("/t/{tenant_slug}/documents/{manual_id}/responsibilities", status_code=201)
def create_responsibility(
    tenant_slug: str,
    manual_id: str,
    payload: ResponsibilityCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    if payload.responsibility_type not in RESPONSIBILITY_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported responsibility type")
    if payload.assignment_source not in ASSIGNMENT_SOURCES or payload.confirmation_status not in CONFIRMATION_STATES:
        raise HTTPException(status_code=422, detail="Unsupported responsibility provenance or state")
    if payload.assignment_source in {"INFERRED", "IMPORTED"} and payload.confirmation_status == "CONFIRMED":
        raise HTTPException(status_code=422, detail="Inferred or imported assignments must be reviewed before confirmation")
    validate_assignment_target(
        assignee_type=payload.assignee_type,
        assignee_user_id=payload.assignee_user_id,
        assignee_department_id=payload.assignee_department_id,
        assignee_org_unit_id=payload.assignee_org_unit_id,
        assignee_role=payload.assignee_role,
    )
    _validate_assignee_tenant(db, tenant=tenant, payload=payload)
    revision_id = None
    if payload.revision_id:
        revision_id = get_revision(db, manual, payload.revision_id).id
    existing = db.query(gm.DocumentResponsibilityAssignment).filter(
        gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
        gm.DocumentResponsibilityAssignment.manual_id == manual.id,
    ).all()
    if incoming_would_replace_confirmed(
        existing,
        responsibility_type=payload.responsibility_type,
        assignment_source=payload.assignment_source,
        confidence_percent=payload.confidence_percent,
    ):
        raise HTTPException(status_code=409, detail="A detected assignment cannot replace a confirmed governed responsibility")
    row = gm.DocumentResponsibilityAssignment(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision_id,
        responsibility_type=payload.responsibility_type,
        assignee_type=payload.assignee_type,
        assignee_user_id=payload.assignee_user_id,
        assignee_department_id=payload.assignee_department_id,
        assignee_org_unit_id=payload.assignee_org_unit_id,
        assignee_role=payload.assignee_role.strip().upper() if payload.assignee_role else None,
        is_primary=payload.is_primary,
        delegated_from_id=payload.delegated_from_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        assignment_source=payload.assignment_source,
        confidence_percent=payload.confidence_percent,
        confirmation_status=payload.confirmation_status,
        provenance_json=dict(payload.provenance),
        created_by_user_id=current_user.id,
        confirmed_by_user_id=current_user.id if payload.confirmation_status == "CONFIRMED" else None,
        confirmed_at=utcnow() if payload.confirmation_status == "CONFIRMED" else None,
    )
    db.add(row)
    db.flush()
    _audit(db, tenant=tenant, user=current_user, request=request, action="document.governance.responsibility_created", entity_type="document_responsibility_assignment", entity_id=row.id, diff={"manual_id": manual.id, "responsibility_type": row.responsibility_type, "source": row.assignment_source, "status": row.confirmation_status})
    db.commit()
    return serialize_assignment(row)


@router.patch("/t/{tenant_slug}/responsibilities/{assignment_id}/decision")
def decide_responsibility(
    tenant_slug: str,
    assignment_id: str,
    payload: GovernanceDecision,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(gm.DocumentResponsibilityAssignment).filter(
        gm.DocumentResponsibilityAssignment.id == assignment_id,
        gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
    ).with_for_update().first()
    if not row:
        raise HTTPException(status_code=404, detail="Responsibility assignment not found")
    if row.confirmation_status == "SUPERSEDED":
        raise HTTPException(status_code=409, detail="A superseded assignment cannot be reviewed")
    row.confirmation_status = payload.decision
    row.confirmed_by_user_id = current_user.id if payload.decision == "CONFIRMED" else None
    row.confirmed_at = utcnow() if payload.decision == "CONFIRMED" else None
    row.provenance_json = {**dict(row.provenance_json or {}), "review_comments": payload.comments}
    _audit(db, tenant=tenant, user=current_user, request=request, action="document.governance.responsibility_decided", entity_type="document_responsibility_assignment", entity_id=row.id, diff={"decision": payload.decision, "comments": payload.comments})
    db.commit()
    return serialize_assignment(row)


@router.post("/t/{tenant_slug}/documents/{manual_id}/relationships", status_code=201)
def create_relationship(
    tenant_slug: str,
    manual_id: str,
    payload: RelationshipCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    if payload.relationship_type not in RELATIONSHIP_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported relationship type")
    if payload.relationship_source not in RELATIONSHIP_SOURCES:
        raise HTTPException(status_code=422, detail="Unsupported relationship provenance")
    if payload.relationship_source in {"EXTRACTED", "INFERRED", "IMPORTED"} and payload.resolution_status == "CONFIRMED":
        raise HTTPException(status_code=422, detail="Detected relationships must be reviewed before confirmation")
    revision = get_revision(db, manual, payload.source_revision_id) if payload.source_revision_id else None
    source_location_id = None
    if payload.source_location:
        if not revision:
            raise HTTPException(status_code=422, detail="A source revision is required for an exact relationship location")
        source_location_id = _location(db, tenant=tenant, manual=manual, revision=revision, payload=payload.source_location).id
    target_manual = None
    target_revision_id = payload.target_revision_id
    if payload.target_manual_id:
        target_manual = get_manual(db, tenant, payload.target_manual_id)
        if target_revision_id:
            target_revision_id = get_revision(db, target_manual, target_revision_id).id
    elif target_revision_id:
        raise HTTPException(status_code=422, detail="target_revision_id requires target_manual_id")
    row = gm.DocumentGovernedRelationship(
        tenant_id=tenant.amo_id,
        source_manual_id=manual.id,
        source_revision_id=revision.id if revision else None,
        source_location_id=source_location_id,
        target_entity_type=payload.target_entity_type.strip().upper(),
        target_entity_id=payload.target_entity_id,
        target_manual_id=target_manual.id if target_manual else None,
        target_revision_id=target_revision_id,
        relationship_type=payload.relationship_type,
        relationship_source=payload.relationship_source,
        occurrence_key=payload.occurrence_key,
        exact_token=payload.exact_token,
        exact_quote=payload.exact_quote,
        page_number=payload.page_number,
        section_label=payload.section_label,
        confidence_percent=payload.confidence_percent,
        resolution_status=payload.resolution_status,
        provenance_json=dict(payload.provenance),
        created_by_user_id=current_user.id,
        confirmed_by_user_id=current_user.id if payload.resolution_status == "CONFIRMED" else None,
        confirmed_at=utcnow() if payload.resolution_status == "CONFIRMED" else None,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This exact relationship occurrence already exists") from exc
    _audit(db, tenant=tenant, user=current_user, request=request, action="document.governance.relationship_created", entity_type="document_governed_relationship", entity_id=row.id, diff={"source_manual_id": manual.id, "relationship_type": row.relationship_type, "source": row.relationship_source, "status": row.resolution_status})
    db.commit()
    return serialize_relationship(row, {target_manual.id: target_manual} if target_manual else {})


@router.patch("/t/{tenant_slug}/governance/references/{reference_id}/decision")
def decide_detected_reference(
    tenant_slug: str,
    reference_id: str,
    payload: GovernanceDecision,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Record a human decision for one exact detected reference occurrence.

    Confirmation is permitted only when the detector already resolved the target to
    an immutable published revision in the same tenant. Unresolved or ambiguous
    matches must first use the existing validated resolution endpoint.
    """
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(km.DocumentationReference).filter(
        km.DocumentationReference.id == reference_id,
        km.DocumentationReference.tenant_id == tenant.amo_id,
    ).with_for_update().first()
    if not row:
        raise HTTPException(status_code=404, detail="Detected reference not found")
    if row.status == "VERIFIED" and payload.decision == "REJECTED":
        raise HTTPException(status_code=409, detail="A verified reference must be superseded through controlled resolution, not silently rejected")

    if payload.decision == "CONFIRMED":
        if not row.target_manual_id or not row.target_revision_id:
            raise HTTPException(status_code=409, detail="Resolve the target document and revision before confirmation")
        target = db.query(manual_models.Manual).filter(
            manual_models.Manual.id == row.target_manual_id,
            manual_models.Manual.tenant_id == tenant.id,
        ).first()
        revision = db.query(manual_models.ManualRevision).filter(
            manual_models.ManualRevision.id == row.target_revision_id,
            manual_models.ManualRevision.manual_id == row.target_manual_id,
        ).first()
        status = str(getattr(getattr(revision, "status_enum", None), "value", getattr(revision, "status_enum", ""))).upper() if revision else ""
        if not target or not revision or status != "PUBLISHED" or not revision.immutable_locked:
            raise HTTPException(status_code=409, detail="A confirmed reference may target only a published immutable revision in this tenant")
        row.status = "VERIFIED"
        row.confidence_percent = 100
        row.verified_by_user_id = current_user.id
        row.verified_at = utcnow()
    else:
        if row.status == "VERIFIED":
            raise HTTPException(status_code=409, detail="A verified reference cannot be rejected in place")
        row.status = "REJECTED"
        row.verified_by_user_id = None
        row.verified_at = None
    row.last_checked_at = utcnow()
    _audit(
        db,
        tenant=tenant,
        user=current_user,
        request=request,
        action="document.governance.reference_decided",
        entity_type="documentation_reference",
        entity_id=row.id,
        diff={
            "decision": payload.decision,
            "comments": payload.comments,
            "target_manual_id": row.target_manual_id,
            "target_revision_id": row.target_revision_id,
        },
    )
    db.commit()
    return {
        "id": row.id,
        "status": row.status,
        "target_manual_id": row.target_manual_id,
        "target_revision_id": row.target_revision_id,
        "confidence_percent": row.confidence_percent,
    }


@router.patch("/t/{tenant_slug}/relationships/{relationship_id}/decision")
def decide_relationship(
    tenant_slug: str,
    relationship_id: str,
    payload: GovernanceDecision,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(gm.DocumentGovernedRelationship).filter(
        gm.DocumentGovernedRelationship.id == relationship_id,
        gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
    ).with_for_update().first()
    if not row:
        raise HTTPException(status_code=404, detail="Governed relationship not found")
    if row.resolution_status == "SUPERSEDED":
        raise HTTPException(status_code=409, detail="A superseded relationship cannot be reviewed")
    row.resolution_status = payload.decision
    row.confirmed_by_user_id = current_user.id if payload.decision == "CONFIRMED" else None
    row.confirmed_at = utcnow() if payload.decision == "CONFIRMED" else None
    row.provenance_json = {**dict(row.provenance_json or {}), "review_comments": payload.comments}
    _audit(db, tenant=tenant, user=current_user, request=request, action="document.governance.relationship_decided", entity_type="document_governed_relationship", entity_id=row.id, diff={"decision": payload.decision, "comments": payload.comments})
    db.commit()
    return serialize_relationship(row)


@router.post("/t/{tenant_slug}/documents/{manual_id}/annotations", status_code=201)
def create_annotation(
    tenant_slug: str,
    manual_id: str,
    payload: AnnotationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    revision = get_revision(db, manual, payload.revision_id)
    if revision.source_sha256 != payload.source_sha256:
        raise HTTPException(status_code=409, detail="The annotation checksum does not match the immutable source revision")
    if payload.visibility in {"AUDIT", "CONTROLLED_RECORD"} and not is_control_user(current_user):
        raise HTTPException(status_code=403, detail="Controlled evidence visibility requires Document Control authority")
    location = _location(db, tenant=tenant, manual=manual, revision=revision, payload=payload.location)
    row = gm.DocumentAnnotation(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        location_id=location.id,
        source_sha256=payload.source_sha256,
        annotation_type=payload.annotation_type,
        color=payload.color,
        visibility=payload.visibility,
        note_text=payload.note_text,
        tags_json=list(dict.fromkeys(tag.strip() for tag in payload.tags if tag.strip())),
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    _audit(db, tenant=tenant, user=current_user, request=request, action="document.annotation.created", entity_type="document_annotation", entity_id=row.id, diff={"manual_id": manual.id, "revision_id": revision.id, "annotation_type": row.annotation_type, "visibility": row.visibility})
    db.commit()
    return {"id": row.id, "location_id": location.id, "revision_id": revision.id, "source_sha256": row.source_sha256, "annotation_type": row.annotation_type, "color": row.color, "visibility": row.visibility, "status": row.status}


@router.post("/t/{tenant_slug}/governance/backfill")
def start_backfill(
    tenant_slug: str,
    payload: BackfillRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    run = create_run(
        db,
        tenant=tenant,
        actor_id=current_user.id,
        idempotency_key=payload.idempotency_key,
        dry_run=payload.dry_run,
        manual_ids=payload.manual_ids,
        reconcile_hierarchy=payload.reconcile_hierarchy,
    )
    run = process_batch(db, tenant=tenant, run_id=run.id, batch_limit=payload.batch_limit, retry_failed=payload.retry_failed)
    _audit(db, tenant=tenant, user=current_user, request=request, action="document.governance.backfill_started", entity_type="document_governance_backfill_run", entity_id=run.id, diff={"dry_run": run.dry_run, "status": run.status, "processed_count": run.processed_count})
    db.commit()
    return serialize_run(db, run)


@router.post("/t/{tenant_slug}/governance/backfill/{run_id}/resume")
def resume_backfill(
    tenant_slug: str,
    run_id: str,
    payload: BackfillResumeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    run = process_batch(db, tenant=tenant, run_id=run_id, batch_limit=payload.batch_limit, retry_failed=payload.retry_failed)
    _audit(db, tenant=tenant, user=current_user, request=request, action="document.governance.backfill_resumed", entity_type="document_governance_backfill_run", entity_id=run.id, diff={"status": run.status, "processed_count": run.processed_count})
    db.commit()
    return serialize_run(db, run)


@router.get("/t/{tenant_slug}/governance/backfill/{run_id}")
def get_backfill(
    tenant_slug: str,
    run_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    run = db.query(gm.DocumentGovernanceBackfillRun).filter(
        gm.DocumentGovernanceBackfillRun.id == run_id,
        gm.DocumentGovernanceBackfillRun.tenant_id == tenant.amo_id,
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Backfill run not found")
    return serialize_run(db, run)
