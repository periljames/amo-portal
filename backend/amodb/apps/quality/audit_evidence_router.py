from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Cookie, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db, get_write_db

from . import models
from .audit_checklist_execution_models import QualityAuditChecklistExecutionEvent
from .audit_checklist_execution_router import (
    ChecklistExecutionUpdate,
    _apply_execution_update,
    _assert_base_version,
    _canonical_from_legacy,
    _governance_snapshot,
    _internal_fieldwork_actor,
    _internal_fieldwork_viewer,
    _item,
    _locked_governance,
    _mark_fieldwork_started,
    _require_fieldwork_write_window,
)
from .audit_evidence_models import QualityAuditEvidenceArtifact
from .audit_evidence_storage import resolve_audit_evidence, store_audit_evidence
from .audit_external_access_models import QualityAuditFindingReleaseEvent
from .audit_external_access_router import (
    FindingReleaseCreate,
    _GUEST_COOKIE,
    _active_grant,
    _append_access_event,
    _audit_for_tenant,
    _latest_release_events,
)
from .audit_external_fieldwork_router import _external_auditor_grant, _require_csrf
from .tenant_security import TenantContext, assert_quality_permission_any, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit evidence"])
public_router = APIRouter(prefix="/quality/audit-access", tags=["Quality / Released Audit Evidence"])


def _artifact_dict(row: QualityAuditEvidenceArtifact) -> dict[str, Any]:
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "checklist_item_id": str(row.checklist_item_id) if row.checklist_item_id else None,
        "finding_id": str(row.finding_id) if row.finding_id else None,
        "source_type": row.source_type,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": int(row.size_bytes or 0),
        "sha256": row.sha256,
        "description": row.description,
        "uploaded_by_user_id": row.uploaded_by_user_id,
        "uploaded_by_participant_id": row.uploaded_by_participant_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _reference(row: QualityAuditEvidenceArtifact) -> dict[str, Any]:
    # Never put a server storage path in checklist/finding JSON. Public release
    # resolves this opaque artifact id back to storage only after authorization.
    return {
        "artifact_id": row.id,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": int(row.size_bytes or 0),
        "sha256": row.sha256,
        "source_type": row.source_type,
    }


def _existing_by_mutation(db: Session, *, amo_id: str, audit_id: uuid.UUID, client_mutation_id: str) -> QualityAuditEvidenceArtifact | None:
    return db.query(QualityAuditEvidenceArtifact).filter(
        QualityAuditEvidenceArtifact.amo_id == amo_id,
        QualityAuditEvidenceArtifact.audit_id == audit_id,
        QualityAuditEvidenceArtifact.client_mutation_id == client_mutation_id,
    ).first()


def _append_reference(
    db: Session,
    *,
    actor_ctx,
    item: models.QualityAuditChecklistItem,
    governance,
    artifact: QualityAuditEvidenceArtifact,
    reason: str,
    participant_id: str | None = None,
):
    current_refs = list(governance.evidence_references or []) if governance else []
    current_status = governance.canonical_response_status if governance else _canonical_from_legacy(item.response_status)
    current_notes = governance.auditor_notes if governance else None
    before_new = set(db.new)
    updated = _apply_execution_update(
        db,
        ctx=actor_ctx,
        item=item,
        payload=ChecklistExecutionUpdate(
            canonical_response_status=current_status,
            auditor_notes=current_notes,
            evidence_references=[*current_refs, _reference(artifact)],
            reason=reason,
        ),
        governance=governance,
    )
    if participant_id:
        updated.updated_by_user_id = None
        updated.updated_by_participant_id = participant_id
        event = next((
            obj for obj in db.new
            if obj not in before_new
            and isinstance(obj, QualityAuditChecklistExecutionEvent)
            and obj.checklist_item_id == item.id
        ), None)
        if event is not None:
            event.actor_user_id = None
            event.actor_participant_id = participant_id
            event.after_snapshot = {**dict(event.after_snapshot or {}), "actor_participant_id": participant_id}
    return updated


@router.get("/audits/{audit_id}/evidence")
def list_audit_evidence(
    audit_id: uuid.UUID,
    checklist_item_id: uuid.UUID | None = None,
    finding_id: uuid.UUID | None = None,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _internal_fieldwork_viewer(db, ctx=ctx, audit_id=audit_id)
    query = db.query(QualityAuditEvidenceArtifact).filter(
        QualityAuditEvidenceArtifact.amo_id == ctx.amo_id,
        QualityAuditEvidenceArtifact.audit_id == audit_id,
    )
    if checklist_item_id is not None:
        query = query.filter(QualityAuditEvidenceArtifact.checklist_item_id == checklist_item_id)
    if finding_id is not None:
        query = query.filter(QualityAuditEvidenceArtifact.finding_id == finding_id)
    rows = query.order_by(QualityAuditEvidenceArtifact.created_at.asc()).limit(1000).all()
    return {"items": [_artifact_dict(row) for row in rows]}


@router.post("/audits/{audit_id}/checklist-items/{item_id}/evidence")
async def upload_internal_audit_evidence(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    base_version: int = Form(...),
    client_mutation_id: str = Form(..., min_length=8, max_length=128),
    description: str | None = Form(default=None, max_length=4000),
    finding_id: uuid.UUID | None = Form(default=None),
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission_any(db, ctx, "qms.audit.manage", "qms.audit.execute")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _internal_fieldwork_actor(db, ctx=ctx, audit_id=audit_id)
    existing = _existing_by_mutation(db, amo_id=ctx.amo_id, audit_id=audit_id, client_mutation_id=client_mutation_id)
    if existing is not None:
        return {"artifact": _artifact_dict(existing), "replayed": True}

    item = _item(db, amo_id=ctx.amo_id, audit_id=audit_id, item_id=item_id, lock=True)
    governance = _locked_governance(db, ctx=ctx, audit_id=audit_id, item_id=item_id)
    _assert_base_version(payload_base_version=base_version, client_mutation_id=client_mutation_id, item=item, governance=governance)
    if finding_id is not None:
        finding = db.query(models.QMSAuditFinding).filter(
            models.QMSAuditFinding.amo_id == ctx.amo_id,
            models.QMSAuditFinding.audit_id == audit_id,
            models.QMSAuditFinding.id == finding_id,
        ).first()
        if finding is None:
            raise HTTPException(status_code=404, detail="Finding not found for this audit.")

    stored = await store_audit_evidence(file, amo_id=ctx.amo_id, audit_id=str(audit_id), checklist_item_id=str(item_id))
    artifact = QualityAuditEvidenceArtifact(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        checklist_item_id=item_id,
        finding_id=finding_id,
        source_type="INTERNAL_USER",
        client_mutation_id=client_mutation_id,
        file_ref=stored.storage_ref,
        filename=stored.filename,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        description=(description or "").strip() or None,
        uploaded_by_user_id=ctx.user_id,
    )
    db.add(artifact)
    db.flush()
    updated = _append_reference(
        db,
        actor_ctx=ctx,
        item=item,
        governance=governance,
        artifact=artifact,
        reason="Governed audit evidence attachment uploaded and linked to checklist execution.",
    )
    db.commit()
    return {"artifact": _artifact_dict(artifact), "committed_version": int(updated.entity_version or 1), "replayed": False}


@router.get("/audits/{audit_id}/evidence/{artifact_id}/download")
def download_internal_audit_evidence(
    audit_id: uuid.UUID,
    artifact_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _internal_fieldwork_viewer(db, ctx=ctx, audit_id=audit_id)
    row = db.query(QualityAuditEvidenceArtifact).filter(
        QualityAuditEvidenceArtifact.id == artifact_id,
        QualityAuditEvidenceArtifact.amo_id == ctx.amo_id,
        QualityAuditEvidenceArtifact.audit_id == audit_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence artifact not found.")
    path = resolve_audit_evidence(row.file_ref)
    return FileResponse(path, filename=row.filename, media_type=row.content_type or "application/octet-stream", headers={"X-Content-SHA256": row.sha256})


@public_router.post("/fieldwork/checklist-items/{item_id}/evidence")
async def upload_external_auditor_evidence(
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    base_version: int = Form(...),
    client_mutation_id: str = Form(..., min_length=8, max_length=128),
    description: str | None = Form(default=None, max_length=4000),
    x_qms_csrf: str | None = Header(default=None, alias="X-QMS-CSRF"),
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    _require_csrf(amo_qms_audit_guest, x_qms_csrf)
    grant = _external_auditor_grant(db, amo_qms_audit_guest, permission="audit:evidence_create")
    participant = grant.participant
    audit = _audit_for_tenant(db, amo_id=grant.amo_id, audit_id=grant.audit_id)
    _require_fieldwork_write_window(db, amo_id=grant.amo_id, audit=audit)
    _mark_fieldwork_started(audit)
    existing = _existing_by_mutation(db, amo_id=grant.amo_id, audit_id=grant.audit_id, client_mutation_id=client_mutation_id)
    if existing is not None:
        return {"artifact": _artifact_dict(existing), "replayed": True}

    actor_ctx = SimpleNamespace(amo_id=grant.amo_id, user_id=None)
    item = _item(db, amo_id=grant.amo_id, audit_id=grant.audit_id, item_id=item_id, lock=True)
    governance = _locked_governance(db, ctx=actor_ctx, audit_id=grant.audit_id, item_id=item_id)
    _assert_base_version(payload_base_version=base_version, client_mutation_id=client_mutation_id, item=item, governance=governance)
    stored = await store_audit_evidence(file, amo_id=grant.amo_id, audit_id=str(grant.audit_id), checklist_item_id=str(item_id))
    artifact = QualityAuditEvidenceArtifact(
        amo_id=grant.amo_id,
        audit_id=grant.audit_id,
        checklist_item_id=item_id,
        source_type="EXTERNAL_AUDITOR",
        client_mutation_id=client_mutation_id,
        file_ref=stored.storage_ref,
        filename=stored.filename,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        description=(description or "").strip() or None,
        uploaded_by_participant_id=participant.id,
    )
    db.add(artifact)
    db.flush()
    updated = _append_reference(
        db,
        actor_ctx=actor_ctx,
        item=item,
        governance=governance,
        artifact=artifact,
        reason=f"External auditor participant {participant.id} uploaded governed checklist evidence.",
        participant_id=participant.id,
    )
    db.commit()
    return {"artifact": _artifact_dict(artifact), "committed_version": int(updated.entity_version or 1), "replayed": False}


@router.post("/audits/{audit_id}/findings/{finding_id}/release")
def release_audit_finding_with_controlled_evidence(
    audit_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: FindingReleaseCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    finding = db.query(models.QMSAuditFinding).filter(
        models.QMSAuditFinding.amo_id == ctx.amo_id,
        models.QMSAuditFinding.audit_id == audit_id,
        models.QMSAuditFinding.id == finding_id,
    ).first()
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found.")

    sanitized: list[dict[str, Any]] = []
    if payload.action == "RELEASED":
        for requested in payload.released_evidence_refs:
            if not isinstance(requested, dict) or not isinstance(requested.get("artifact_id"), str):
                raise HTTPException(status_code=422, detail="Released file evidence must reference a governed evidence artifact id; raw storage paths and free-form file references are not permitted.")
            artifact = db.query(QualityAuditEvidenceArtifact).filter(
                QualityAuditEvidenceArtifact.id == requested["artifact_id"],
                QualityAuditEvidenceArtifact.amo_id == ctx.amo_id,
                QualityAuditEvidenceArtifact.audit_id == audit_id,
            ).first()
            if artifact is None:
                raise HTTPException(status_code=404, detail="A selected evidence artifact does not belong to this audit.")
            related = artifact.finding_id == finding_id
            if not related and artifact.checklist_item_id is not None:
                related = db.query(models.QualityAuditChecklistItem.id).filter(
                    models.QualityAuditChecklistItem.amo_id == ctx.amo_id,
                    models.QualityAuditChecklistItem.audit_id == audit_id,
                    models.QualityAuditChecklistItem.id == artifact.checklist_item_id,
                    models.QualityAuditChecklistItem.finding_id == finding_id,
                ).first() is not None
            if not related:
                raise HTTPException(status_code=409, detail="Evidence can only be released with the finding it governs.")
            sanitized.append(_reference(artifact))

    event = QualityAuditFindingReleaseEvent(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        finding_id=finding_id,
        action=payload.action,
        include_objective_evidence=payload.include_objective_evidence,
        released_evidence_refs=sanitized,
        reason=payload.reason.strip(),
        actor_user_id=ctx.user_id,
    )
    db.add(event)
    db.commit()
    return {
        "finding_id": str(finding_id),
        "action": event.action,
        "released_at": event.created_at.isoformat(),
        "include_objective_evidence": event.include_objective_evidence,
        "released_evidence_refs": event.released_evidence_refs,
    }


@public_router.get("/findings/{finding_id}/evidence/{artifact_id}/download")
def download_released_audit_evidence(
    finding_id: uuid.UUID,
    artifact_id: str,
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
):
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    participant = grant.participant
    scope = set(grant.scope_json or [])
    if participant is None or participant.participant_type != "AUDITEE_GUEST" or "audit:read_released_evidence" not in scope:
        raise HTTPException(status_code=403, detail="This audit access grant cannot read released evidence.")
    latest = _latest_release_events(db, amo_id=grant.amo_id, audit_id=grant.audit_id).get(finding_id)
    if latest is None or latest.action != "RELEASED":
        raise HTTPException(status_code=404, detail="Released evidence not found.")
    permitted_ids = {
        str(ref.get("artifact_id"))
        for ref in list(latest.released_evidence_refs or [])
        if isinstance(ref, dict) and ref.get("artifact_id")
    }
    if artifact_id not in permitted_ids:
        raise HTTPException(status_code=404, detail="Released evidence not found.")
    row = db.query(QualityAuditEvidenceArtifact).filter(
        QualityAuditEvidenceArtifact.id == artifact_id,
        QualityAuditEvidenceArtifact.amo_id == grant.amo_id,
        QualityAuditEvidenceArtifact.audit_id == grant.audit_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Released evidence not found.")
    path = resolve_audit_evidence(row.file_ref)
    _append_access_event(db, grant, "READ", f"Released evidence artifact {row.id} downloaded for finding {finding_id}.")
    db.commit()
    return FileResponse(path, filename=row.filename, media_type=row.content_type or "application/octet-stream", headers={"X-Content-SHA256": row.sha256})
