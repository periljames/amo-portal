from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control import knowledge_models as km
from amodb.apps.doc_control.knowledge_service import (
    create_documentation_record,
    hierarchy_payload,
    index_revision_background,
    readable_reference_payload,
    serialize_execution_profile,
    serialize_record,
)
from amodb.apps.doc_control.workspace_service import can_read_manual, get_profile, is_control_user
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models
from .publications_fast_reader_router import _load_publication
from .core_router import _tenant_by_slug


router = APIRouter(prefix="/manuals", tags=["Publications Knowledge Graph"])


def _source_type(revision: models.ManualRevision) -> str:
    return str(getattr(revision.source_type_enum, "value", revision.source_type_enum or "")).upper()


def _render_path(tenant_slug: str, manual_id: str, revision: models.ManualRevision) -> str:
    endpoint = "stream.pdf" if _source_type(revision) == "PDF" else "rendered.pdf"
    return f"/manuals/t/{tenant_slug}/{manual_id}/rev/{revision.id}/{endpoint}"


def _resolved_target_revision(
    db: Session,
    reference: km.DocumentationReference,
    target: models.Manual,
) -> models.ManualRevision | None:
    revision_id = (
        target.current_published_rev_id
        if reference.resolution_policy == "CURRENT_EFFECTIVE"
        else reference.target_revision_id
    )
    if not revision_id:
        return None
    return (
        db.query(models.ManualRevision)
        .filter(
            models.ManualRevision.id == revision_id,
            models.ManualRevision.manual_id == target.id,
            models.ManualRevision.status_enum == models.ManualRevisionStatus.PUBLISHED,
            models.ManualRevision.immutable_locked.is_(True),
        )
        .first()
    )


def _target_payload(
    *,
    tenant: models.Tenant,
    target: models.Manual,
    revision: models.ManualRevision,
    node: km.DocumentationNode | None,
    execution: km.DocumentationExecutionProfile | None,
    indexed_revision_id: str | None,
    resolution_policy: str,
) -> dict:
    document_path = _render_path(tenant.slug, target.id, revision)
    payload = {
        "manual_id": target.id,
        "revision_id": revision.id,
        "code": target.code,
        "title": target.title,
        "manual_type": target.manual_type,
        "node_type": node.node_type if node else None,
        "hierarchy_path": node.path if node else None,
        "reader_url": f"/maintenance/{tenant.slug.upper()}/publications/{target.id}/rev/{revision.id}/read",
        "pdf_url": document_path,
        "download_url": document_path,
        "execution": serialize_execution_profile(execution),
    }
    if resolution_policy == "CURRENT_EFFECTIVE" and indexed_revision_id and indexed_revision_id != revision.id:
        payload["advanced_from_indexed_revision"] = indexed_revision_id
    return payload


def _refresh_current_effective_payload(
    db: Session,
    *,
    tenant: models.Tenant,
    user: account_models.User,
    payload: dict,
) -> dict:
    items = list(payload.get("items") or [])
    reference_ids = [str(item.get("id")) for item in items if item.get("id")]
    references = {
        row.id: row
        for row in db.query(km.DocumentationReference)
        .filter(
            km.DocumentationReference.id.in_(reference_ids or ["-"]),
            km.DocumentationReference.tenant_id == tenant.amo_id,
        )
        .all()
    }
    target_ids = {row.target_manual_id for row in references.values() if row.target_manual_id}
    manuals = {
        row.id: row
        for row in db.query(models.Manual)
        .filter(models.Manual.id.in_(target_ids or ["-"]), models.Manual.tenant_id == tenant.id)
        .all()
    }
    execution_profiles = {
        row.manual_id: row
        for row in db.query(km.DocumentationExecutionProfile)
        .filter(
            km.DocumentationExecutionProfile.tenant_id == tenant.amo_id,
            km.DocumentationExecutionProfile.manual_id.in_(target_ids or ["-"]),
        )
        .all()
    }
    nodes = {
        row.manual_id: row
        for row in db.query(km.DocumentationNode)
        .filter(
            km.DocumentationNode.tenant_id == tenant.amo_id,
            km.DocumentationNode.manual_id.in_(target_ids or ["-"]),
        )
        .all()
    }

    for item in items:
        reference = references.get(item.get("id"))
        target = manuals.get(reference.target_manual_id) if reference and reference.target_manual_id else None
        if not reference or not target:
            item["target"] = None
            if reference and reference.target_manual_id:
                item["status"] = "BROKEN"
            continue
        profile = get_profile(db, tenant, target.id)
        if not can_read_manual(user, profile):
            item["target"] = None
            item["status"] = "RESTRICTED"
            item["candidates"] = []
            continue
        revision = _resolved_target_revision(db, reference, target)
        if not revision:
            item["target"] = None
            item["status"] = "BROKEN"
            continue
        item["target"] = _target_payload(
            tenant=tenant,
            target=target,
            revision=revision,
            node=nodes.get(target.id),
            execution=execution_profiles.get(target.id),
            indexed_revision_id=reference.target_revision_id,
            resolution_policy=reference.resolution_policy,
        )
    payload["items"] = items
    return payload


@router.get("/t/{tenant_slug}/knowledge-tree")
def publication_knowledge_tree(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    if not getattr(current_user, "is_superuser", False) and str(current_user.amo_id) != str(tenant.amo_id):
        raise HTTPException(status_code=403, detail="The requested hierarchy is outside the active AMO")
    payload = hierarchy_payload(
        db,
        manual_tenant=tenant,
        actor_id=current_user.id if is_control_user(current_user) else None,
    )
    db.commit()
    payload["capabilities"] = {"read": True, "control": is_control_user(current_user)}
    return payload


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/references")
def publication_references(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    background_tasks: BackgroundTasks,
    page: int | None = None,
    section_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant, _manual, revision, _profile = _load_publication(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    job = (
        db.query(km.DocumentationIndexJob)
        .filter(
            km.DocumentationIndexJob.tenant_id == tenant.amo_id,
            km.DocumentationIndexJob.revision_id == revision.id,
        )
        .first()
    )
    stale = not job or job.source_sha256 != revision.source_sha256 or int(job.index_version or 0) < 1
    if stale and (not job or job.status not in {"PENDING", "RUNNING"}):
        if not job:
            job = km.DocumentationIndexJob(
                tenant_id=tenant.amo_id,
                manual_id=manual_id,
                revision_id=revision.id,
                source_sha256=revision.source_sha256,
                status="PENDING",
            )
            db.add(job)
        else:
            job.status = "PENDING"
            job.source_sha256 = revision.source_sha256
            job.error_summary = None
        db.commit()
        background_tasks.add_task(index_revision_background, revision.id)
    payload = readable_reference_payload(
        db,
        manual_tenant=tenant,
        source_revision_id=revision.id,
        user=current_user,
        page=page,
        section_id=section_id,
    )
    return _refresh_current_effective_payload(db, tenant=tenant, user=current_user, payload=payload)


@router.get("/t/{tenant_slug}/linked-resources/{reference_id}")
def linked_resource_detail(
    tenant_slug: str,
    reference_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    if not getattr(current_user, "is_superuser", False) and str(current_user.amo_id) != str(tenant.amo_id):
        raise HTTPException(status_code=403, detail="The linked resource is outside the active AMO")
    reference = (
        db.query(km.DocumentationReference)
        .filter(
            km.DocumentationReference.id == reference_id,
            km.DocumentationReference.tenant_id == tenant.amo_id,
        )
        .first()
    )
    if not reference or not reference.target_manual_id:
        raise HTTPException(status_code=404, detail="The document reference is unresolved")
    target = (
        db.query(models.Manual)
        .filter(models.Manual.id == reference.target_manual_id, models.Manual.tenant_id == tenant.id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="The linked controlled resource is unavailable")
    revision = _resolved_target_revision(db, reference, target)
    if not revision:
        raise HTTPException(status_code=409, detail="The linked controlled resource has no effective immutable revision")
    profile = get_profile(db, tenant, target.id)
    from amodb.apps.doc_control.workspace_service import require_manual_access

    require_manual_access(current_user, profile)
    execution = (
        db.query(km.DocumentationExecutionProfile)
        .filter(
            km.DocumentationExecutionProfile.tenant_id == tenant.amo_id,
            km.DocumentationExecutionProfile.manual_id == target.id,
        )
        .first()
    )
    node = (
        db.query(km.DocumentationNode)
        .filter(km.DocumentationNode.tenant_id == tenant.amo_id, km.DocumentationNode.manual_id == target.id)
        .first()
    )
    source_manual = db.query(models.Manual).filter(models.Manual.id == reference.source_manual_id).first()
    target_payload = _target_payload(
        tenant=tenant,
        target=target,
        revision=revision,
        node=node,
        execution=execution,
        indexed_revision_id=reference.target_revision_id,
        resolution_policy=reference.resolution_policy,
    )
    target_payload.update(
        {
            "issue_number": revision.issue_number,
            "revision_number": revision.rev_number,
            "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
            "status": str(getattr(revision.status_enum, "value", revision.status_enum)),
            "immutable": bool(revision.immutable_locked),
            "source_type": _source_type(revision),
            "source_filename": revision.source_filename,
            "page_count": revision.source_page_count,
            "node": {"id": node.id, "node_type": node.node_type, "path": node.path} if node else None,
        }
    )
    return {
        "reference": {
            "id": reference.id,
            "raw_token": reference.raw_token,
            "relationship_type": reference.relationship_type,
            "resolution_policy": reference.resolution_policy,
            "status": reference.status,
            "source_manual_id": reference.source_manual_id,
            "source_revision_id": reference.source_revision_id,
            "source_page_number": reference.source_page_number,
            "source_context": reference.source_context,
            "source_document": {"code": source_manual.code, "title": source_manual.title} if source_manual else None,
        },
        "target": target_payload,
        "capabilities": {
            "download": bool(execution.allow_download if execution else True),
            "execute": bool(
                execution
                and execution.submission_mode in {"FILL_AND_SUBMIT", "DOWNLOAD_AND_UPLOAD", "PORTAL_SUBMISSION"}
            ),
            "save_draft": bool(execution and execution.allow_save_draft),
        },
    }


@router.post("/t/{tenant_slug}/linked-resources/{reference_id}/submit")
async def submit_linked_resource(
    tenant_slug: str,
    reference_id: str,
    request: Request,
    artifact: UploadFile = File(...),
    payload_json: str = Form("{}"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    if not getattr(current_user, "is_superuser", False) and str(current_user.amo_id) != str(tenant.amo_id):
        raise HTTPException(status_code=403, detail="The linked resource is outside the active AMO")
    reference = (
        db.query(km.DocumentationReference)
        .filter(
            km.DocumentationReference.id == reference_id,
            km.DocumentationReference.tenant_id == tenant.amo_id,
        )
        .first()
    )
    if not reference or not reference.target_manual_id:
        raise HTTPException(status_code=404, detail="The document reference is unresolved")
    template = (
        db.query(models.Manual)
        .filter(models.Manual.id == reference.target_manual_id, models.Manual.tenant_id == tenant.id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="The controlled template is unavailable")
    revision = _resolved_target_revision(db, reference, template)
    execution = (
        db.query(km.DocumentationExecutionProfile)
        .filter(
            km.DocumentationExecutionProfile.tenant_id == tenant.amo_id,
            km.DocumentationExecutionProfile.manual_id == reference.target_manual_id,
        )
        .first()
    )
    if not revision or not execution:
        raise HTTPException(
            status_code=409,
            detail="This linked item is not configured as an effective executable controlled template",
        )
    if execution.submission_mode not in {"FILL_AND_SUBMIT", "DOWNLOAD_AND_UPLOAD", "PORTAL_SUBMISSION"}:
        raise HTTPException(status_code=409, detail="This controlled resource is available for download only")
    profile = get_profile(db, tenant, template.id)
    from amodb.apps.doc_control.workspace_service import require_manual_access

    require_manual_access(current_user, profile)
    try:
        payload = json.loads(payload_json or "{}")
        if not isinstance(payload, dict):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Submission metadata must be a JSON object") from exc
    content = await artifact.read()
    record = create_documentation_record(
        db,
        manual_tenant=tenant,
        template=template,
        revision=revision,
        profile=execution,
        actor_id=current_user.id,
        filename=artifact.filename or f"{template.code}.pdf",
        content=content,
        source_reference_id=reference.id,
        payload=payload,
    )
    db.add(
        models.ManualAuditLog(
            tenant_id=tenant.id,
            actor_id=current_user.id,
            action="documentation.record.submitted",
            entity_type="documentation_record",
            entity_id=record.id,
            ip_device=(
                f"{request.client.host if request.client else 'unknown'}::"
                f"{request.headers.get('user-agent', 'n/a')}"
            ),
            diff_json={
                "record_number": record.record_number,
                "template_manual_id": template.id,
                "template_revision_id": revision.id,
                "source_reference_id": reference.id,
                "artifact_sha256": record.artifact_sha256,
                "resolution_policy": reference.resolution_policy,
            },
        )
    )
    db.commit()
    db.refresh(record)
    result = serialize_record(record)
    result["download_url"] = f"/manuals/t/{tenant.slug}/records/{record.id}/artifact.pdf"
    return result


@router.get("/t/{tenant_slug}/records/{record_id}/artifact.pdf")
def download_documentation_record(
    tenant_slug: str,
    record_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    if not getattr(current_user, "is_superuser", False) and str(current_user.amo_id) != str(tenant.amo_id):
        raise HTTPException(status_code=403, detail="The retained record is outside the active AMO")
    row = (
        db.query(km.DocumentationRecord)
        .filter(km.DocumentationRecord.id == record_id, km.DocumentationRecord.tenant_id == tenant.amo_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Retained record not found")
    if not is_control_user(current_user) and row.submitted_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the submitter or Document Control may open this retained record")
    path = Path(row.artifact_storage_path).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="The retained record artifact is unavailable")
    return FileResponse(
        path,
        media_type=row.artifact_mime_type,
        filename=row.artifact_filename,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": row.artifact_sha256,
            "X-Record-Number": row.record_number,
        },
    )
