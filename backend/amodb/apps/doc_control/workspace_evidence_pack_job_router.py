from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import saas_models, saas_queue
from amodb.database import get_db
from amodb.security import get_current_active_user

from .evidence_pack_job_service import JOB_TYPE, QUEUE_NAME, verified_job_output
from .workspace_service import (
    audit,
    get_manual,
    get_profile,
    get_revision,
    require_control_user,
    require_manual_access,
    resolve_tenant,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Evidence Pack Jobs"])


def _job_for_document(
    db: Session,
    *,
    tenant_id: str,
    manual_id: str,
    job_id: str,
) -> saas_models.SaaSJob:
    job = (
        db.query(saas_models.SaaSJob)
        .filter(
            saas_models.SaaSJob.id == job_id,
            saas_models.SaaSJob.job_type == JOB_TYPE,
            saas_models.SaaSJob.tenant_id == tenant_id,
        )
        .first()
    )
    if not job or str((job.payload_json or {}).get("manual_id") or "") != str(manual_id):
        raise HTTPException(status_code=404, detail="Evidence pack job not found")
    return job


def _serialize_job(job: saas_models.SaaSJob, *, tenant_slug: str, manual_id: str) -> dict:
    result = dict(job.result_json or {}) if isinstance(job.result_json, dict) else {}
    return {
        "job_id": job.id,
        "status": job.status,
        "manual_id": manual_id,
        "revision_id": (job.payload_json or {}).get("revision_id"),
        "requested_at": job.created_at,
        "started_at": job.locked_at,
        "finished_at": job.finished_at,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "error": job.last_error if job.status in {"FAILED", "DEAD"} else None,
        "filename": result.get("filename"),
        "sha256": result.get("sha256"),
        "size_bytes": result.get("size_bytes"),
        "attachments": result.get("attachments"),
        "download_url": (
            f"/doc-control/workspace/t/{tenant_slug}/documents/{manual_id}/evidence-pack-jobs/{job.id}/download"
            if job.status == "SUCCEEDED" else None
        ),
    }


@router.post("/t/{tenant_slug}/documents/{manual_id}/evidence-pack-jobs")
def create_evidence_pack_job(
    tenant_slug: str,
    manual_id: str,
    request: Request,
    revision_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    profile = get_profile(db, tenant, manual.id)
    require_manual_access(current_user, profile)
    if revision_id:
        get_revision(db, manual, revision_id)

    job = saas_queue.enqueue_job(
        db,
        job_type=JOB_TYPE,
        queue_name=QUEUE_NAME,
        tenant_id=tenant.amo_id,
        payload={
            "manual_id": manual.id,
            "revision_id": revision_id,
            "requested_by_user_id": current_user.id,
            "tenant_slug": tenant.slug,
        },
        idempotency_key=f"evidence-pack:{manual.id}:{uuid4().hex}",
        correlation_id=f"document-evidence-pack:{manual.id}",
        created_by=current_user.id,
        max_attempts=3,
        commit=False,
    )
    audit(
        db,
        tenant,
        request,
        "document.evidence_pack.queued",
        "manual",
        manual.id,
        {"job_id": job.id, "revision_id": revision_id, "queue": QUEUE_NAME},
    )
    db.commit()
    db.refresh(job)
    return _serialize_job(job, tenant_slug=tenant.slug, manual_id=manual.id)


@router.get("/t/{tenant_slug}/documents/{manual_id}/evidence-pack-jobs/{job_id}")
def evidence_pack_job_status(
    tenant_slug: str,
    manual_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    job = _job_for_document(db, tenant_id=tenant.amo_id, manual_id=manual.id, job_id=job_id)
    return _serialize_job(job, tenant_slug=tenant.slug, manual_id=manual.id)


@router.get("/t/{tenant_slug}/documents/{manual_id}/evidence-pack-jobs/{job_id}/download")
def download_evidence_pack_job(
    tenant_slug: str,
    manual_id: str,
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    job = _job_for_document(db, tenant_id=tenant.amo_id, manual_id=manual.id, job_id=job_id)
    path, result = verified_job_output(job)
    audit(
        db,
        tenant,
        request,
        "document.evidence_pack.job_downloaded",
        "manual",
        manual.id,
        {"job_id": job.id, "revision_id": (job.payload_json or {}).get("revision_id"), "pack_sha256": result.get("sha256")},
    )
    db.commit()
    return FileResponse(
        path,
        media_type="application/zip",
        filename=str(result.get("filename") or "document-evidence-pack.zip"),
        headers={
            "Cache-Control": "private, no-store",
            "X-Evidence-Pack-SHA256": str(result.get("sha256") or ""),
            "X-Evidence-Pack-Attachments": str(result.get("attachments") or 0),
            "X-Evidence-Pack-Job": job.id,
        },
    )
