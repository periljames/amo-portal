"""Platform diagnostics and approved recovery for retained training imports."""
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.apps.platform import models as platform_models, services as platform_services
from amodb.apps.platform.router import require_platform_superuser, create_support_session
from .workbook_models import TrainingWorkbookImportJob
from .workbook_import import process_workbook_preview, utcnow
from .workbook_router import _job_read, _queue_commit, _rows_page
from .workbook_schemas import WorkbookImportCommitRequest

router = APIRouter(prefix="/platform/training-workbook-imports", tags=["platform-training-support"])


class SupportOpenRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


def _support_session(db, user, tenant_id, *, write=False):
    query = db.query(platform_models.PlatformTenantSupportSession).filter(
        platform_models.PlatformTenantSupportSession.tenant_id == tenant_id,
        platform_models.PlatformTenantSupportSession.platform_user_id == user.id,
        platform_models.PlatformTenantSupportSession.status == "ACTIVE",
        platform_models.PlatformTenantSupportSession.ended_at.is_(None),
        platform_models.PlatformTenantSupportSession.expires_at > utcnow(),
    )
    if write:
        query = query.filter(
            platform_models.PlatformTenantSupportSession.access_level == "ADMIN",
            platform_models.PlatformTenantSupportSession.approved_by_user_id.isnot(None),
        )
    return query.first()


def _support_job(db, user, job_id, *, write=False):
    job = db.get(TrainingWorkbookImportJob, job_id)
    if job is None:
        raise HTTPException(404, "Training workbook import not found.")
    if not _support_session(db, user, job.amo_id, write=write):
        raise HTTPException(
            403,
            "An active tenant-approved ADMIN support session is required."
            if write
            else "Open this job with a support reason first.",
        )
    return job


def _read(db, job, user):
    result = _job_read(db, job)
    result.summary = {
        **result.summary,
        "support_can_manage": bool(_support_session(db, user, job.amo_id, write=True)),
        "support_session_active": bool(_support_session(db, user, job.amo_id, write=False)),
    }
    return result


def _audit(db, job, user, action):
    session = _support_session(db, user, job.amo_id, write=True)
    if session is None:
        raise HTTPException(403, "An active tenant-approved ADMIN support session is required.")
    platform_services.audit(
        db,
        actor_user_id=user.id,
        action=action,
        tenant_id=job.amo_id,
        entity_type="training.workbook_import",
        entity_id=job.id,
        reason=session.reason,
        details={"support_session_id": session.id},
    )


@router.post("/{job_id}/open")
def open_job(
    job_id: str,
    payload: SupportOpenRequest,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    job = db.get(TrainingWorkbookImportJob, job_id)
    if job is None:
        raise HTTPException(404, "Training workbook import not found.")
    # Ensure a readable support session exists for this platform user + tenant.
    if not _support_session(db, user, job.amo_id):
        create_support_session(
            job.amo_id,
            {
                "access_level": "READ_ONLY",
                "reason": payload.reason,
                "ticket_reference": job.id,
            },
            db,
            user,
        )
    platform_services.audit(
        db,
        actor_user_id=user.id,
        action="training.import.support_opened",
        tenant_id=job.amo_id,
        entity_type="training.workbook_import",
        entity_id=job.id,
        reason=payload.reason,
        details={},
    )
    db.commit()
    db.refresh(job)
    return _read(db, job, user)


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    return _read(db, _support_job(db, user, job_id), user)


@router.get("/{job_id}/rows")
def rows(
    job_id: str,
    sheet: str | None = None,
    row_status: str | None = Query(None, alias="status"),
    outcome: str | None = None,
    review_only: bool = False,
    q: str | None = None,
    limit: int = Query(80, ge=1, le=250),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    return _rows_page(
        db,
        _support_job(db, user, job_id),
        sheet=sheet,
        row_status=row_status,
        outcome=outcome,
        review_only=review_only,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.post("/{job_id}/commit", status_code=202)
def commit(
    job_id: str,
    payload: WorkbookImportCommitRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    job = _support_job(db, user, job_id, write=True)
    _audit(db, job, user, "training.import.support_commit")
    result = _queue_commit(db, job, payload, background_tasks, user.id)
    result.summary = {**result.summary, "support_can_manage": True, "support_session_active": True}
    return result


@router.post("/{job_id}/recheck", status_code=202)
def recheck(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    job = _support_job(db, user, job_id, write=True)
    if job.status not in {"COMPLETED", "FAILED", "CANCELLED"}:
        raise HTTPException(409, "Finish the current job before rechecking its workbook.")
    _audit(db, job, user, "training.import.support_recheck")
    retry = TrainingWorkbookImportJob(
        amo_id=job.amo_id,
        actor_user_id=user.id,
        filename=job.filename,
        storage_path=job.storage_path,
        content_type=job.content_type,
        size_bytes=job.size_bytes,
        file_sha256=job.file_sha256,
        idempotency_key=f"support-recheck:{uuid4()}",
        duplicate_of_job_id=job.id if job.committed_at else None,
        summary_json={"recheck_of_job_id": job.id},
    )
    db.add(retry)
    db.commit()
    db.refresh(retry)
    background_tasks.add_task(process_workbook_preview, retry.id)
    return _read(db, retry, user)


@router.post("/{job_id}/cancel")
def cancel(job_id: str, db: Session = Depends(get_db), user=Depends(require_platform_superuser)):
    job = _support_job(db, user, job_id, write=True)
    if job.status in {"COMPLETED", "FAILED", "CANCELLED"}:
        raise HTTPException(409, "This job is already finished.")
    _audit(db, job, user, "training.import.support_cancel")
    job.cancel_requested = True
    db.commit()
    return _read(db, job, user)
