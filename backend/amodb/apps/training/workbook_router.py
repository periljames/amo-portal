from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import compliance as training_compliance
from .workbook_import import commit_workbook_import, process_workbook_preview, utcnow
from .workbook_models import (
    PersonnelLicence,
    TrainingCourseRoleRule,
    TrainingPersonRole,
    TrainingRoleGroup,
    TrainingWorkbookImportJob,
    TrainingWorkbookImportRow,
    TrainingWorkbookImportSheet,
)
from .workbook_schemas import (
    PersonnelLicenceRead,
    TrainingCourseRoleRuleRead,
    TrainingPersonRoleRead,
    TrainingRoleGroupRead,
    TrainingWorkbookImportJobRead,
    WorkbookImportCommitRequest,
    WorkbookImportRowPage,
    WorkbookImportRowRead,
    WorkbookImportSheetRead,
)

router = APIRouter(prefix="/workbook-imports", tags=["training-workbook-imports"])

_IMPORT_DIR = Path(os.getenv("TRAINING_UPLOAD_DIR", "uploads/training")).resolve() / "workbook-imports"
_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
_MAX_BYTES = int(os.getenv("TRAINING_WORKBOOK_MAX_UPLOAD_BYTES", str(40 * 1024 * 1024)))


def _editor(current_user: account_models.User = Depends(get_current_active_user)) -> account_models.User:
    if not training_compliance.is_training_editor(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Training import permission required.")
    return current_user


def _job_for_user(db: Session, current_user: account_models.User, job_id: str) -> TrainingWorkbookImportJob:
    query = db.query(TrainingWorkbookImportJob).filter(TrainingWorkbookImportJob.id == job_id)
    if not current_user.is_superuser:
        query = query.filter(TrainingWorkbookImportJob.amo_id == current_user.amo_id)
    job = query.first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training workbook import not found.")
    return job


def _sheet_read(item: TrainingWorkbookImportSheet) -> WorkbookImportSheetRead:
    return WorkbookImportSheetRead.model_validate(item)


def _job_read(db: Session, job: TrainingWorkbookImportJob) -> TrainingWorkbookImportJobRead:
    sheets = (
        db.query(TrainingWorkbookImportSheet)
        .filter(TrainingWorkbookImportSheet.job_id == job.id)
        .order_by(TrainingWorkbookImportSheet.display_order.asc())
        .all()
    )
    return TrainingWorkbookImportJobRead(
        id=job.id,
        amo_id=job.amo_id,
        actor_user_id=job.actor_user_id,
        filename=job.filename,
        size_bytes=job.size_bytes,
        file_sha256=job.file_sha256,
        duplicate_of_job_id=job.duplicate_of_job_id,
        status=job.status,
        stage=job.stage,
        current_sheet=job.current_sheet,
        current_record_label=job.current_record_label,
        processed_rows=job.processed_rows,
        total_rows=job.total_rows,
        created_count=job.created_count,
        updated_count=job.updated_count,
        unchanged_count=job.unchanged_count,
        skipped_count=job.skipped_count,
        failed_count=job.failed_count,
        review_count=job.review_count,
        summary=job.summary_json or {},
        error_message=job.error_message,
        cancel_requested=job.cancel_requested,
        created_at=job.created_at,
        started_at=job.started_at,
        preview_completed_at=job.preview_completed_at,
        committed_at=job.committed_at,
        completed_at=job.completed_at,
        updated_at=job.updated_at,
        sheets=[_sheet_read(item) for item in sheets],
    )


@router.post("", response_model=TrainingWorkbookImportJobRead, status_code=status.HTTP_202_ACCEPTED)
async def create_workbook_import(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    idempotency_key: Optional[str] = Query(default=None, max_length=160),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_editor),
) -> TrainingWorkbookImportJobRead:
    filename = Path(file.filename or "training-workbook.xlsx").name
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if extension not in {"xlsx", "xlsm", "xltx", "xltm"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload a modern Excel .xlsx or .xlsm training workbook.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded workbook is empty.")
    if _MAX_BYTES and len(content) > _MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"Workbook exceeds the {_MAX_BYTES // (1024 * 1024)} MB import limit.")

    sha = hashlib.sha256(content).hexdigest()
    key = (idempotency_key or f"preview:{sha}:{current_user.id}").strip()
    existing_key = db.query(TrainingWorkbookImportJob).filter(
        TrainingWorkbookImportJob.amo_id == current_user.amo_id,
        TrainingWorkbookImportJob.idempotency_key == key,
    ).first()
    if existing_key:
        return _job_read(db, existing_key)

    duplicate = db.query(TrainingWorkbookImportJob).filter(
        TrainingWorkbookImportJob.amo_id == current_user.amo_id,
        TrainingWorkbookImportJob.file_sha256 == sha,
        TrainingWorkbookImportJob.status == "COMPLETED",
        TrainingWorkbookImportJob.committed_at.isnot(None),
    ).order_by(TrainingWorkbookImportJob.committed_at.desc()).first()

    amo_dir = _IMPORT_DIR / str(current_user.amo_id)
    amo_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or "training-workbook.xlsx"
    storage_path = amo_dir / f"{sha[:16]}-{safe_stem}"
    if not storage_path.exists():
        temporary = storage_path.with_suffix(storage_path.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(storage_path)

    job = TrainingWorkbookImportJob(
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        filename=filename,
        content_type=file.content_type,
        size_bytes=len(content),
        file_sha256=sha,
        storage_path=str(storage_path),
        idempotency_key=key,
        duplicate_of_job_id=duplicate.id if duplicate else None,
        status="QUEUED",
        stage="UPLOAD_COMPLETE",
        summary_json={"duplicate_committed_import": duplicate.id if duplicate else None},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(process_workbook_preview, job.id)
    return _job_read(db, job)


@router.get("/{job_id}", response_model=TrainingWorkbookImportJobRead)
def get_workbook_import(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_editor),
) -> TrainingWorkbookImportJobRead:
    return _job_read(db, _job_for_user(db, current_user, job_id))


@router.get("/{job_id}/rows", response_model=WorkbookImportRowPage)
def list_workbook_import_rows(
    job_id: str,
    sheet: Optional[str] = None,
    row_status: Optional[str] = Query(default=None, alias="status"),
    review_only: bool = False,
    q: Optional[str] = None,
    limit: int = Query(default=80, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_editor),
) -> WorkbookImportRowPage:
    job = _job_for_user(db, current_user, job_id)
    query = db.query(TrainingWorkbookImportRow).filter(TrainingWorkbookImportRow.job_id == job.id)
    if sheet:
        query = query.filter(TrainingWorkbookImportRow.sheet_name == sheet)
    if row_status:
        query = query.filter(TrainingWorkbookImportRow.status == row_status.upper())
    if review_only:
        query = query.filter(TrainingWorkbookImportRow.decision_required.is_(True))
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(or_(TrainingWorkbookImportRow.display_label.ilike(term), TrainingWorkbookImportRow.source_key.ilike(term), TrainingWorkbookImportRow.issue_message.ilike(term)))
    total = query.count()
    rows = query.order_by(TrainingWorkbookImportRow.sheet_name.asc(), TrainingWorkbookImportRow.source_row.asc()).offset(offset).limit(limit).all()
    return WorkbookImportRowPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            WorkbookImportRowRead(
                id=item.id,
                sheet_name=item.sheet_name,
                source_row=item.source_row,
                entity_type=item.entity_type,
                source_key=item.source_key,
                display_label=item.display_label,
                proposed_action=item.proposed_action,
                status=item.status,
                decision_required=item.decision_required,
                decision=item.decision,
                decision_options=item.decision_options or [],
                changes=item.changes_json or [],
                issue_code=item.issue_code,
                issue_message=item.issue_message,
                payload=item.payload_json or {},
                committed_entity_id=item.committed_entity_id,
            )
            for item in rows
        ],
    )


@router.post("/{job_id}/commit", response_model=TrainingWorkbookImportJobRead, status_code=status.HTTP_202_ACCEPTED)
def commit_import(
    job_id: str,
    payload: WorkbookImportCommitRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_editor),
) -> TrainingWorkbookImportJobRead:
    job = _job_for_user(db, current_user, job_id)
    if job.status not in {"PREVIEW_READY", "REVIEW_REQUIRED", "FAILED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Import is currently {job.status.lower()} and cannot be committed.")
    rows_by_id = {
        item.id: item
        for item in db.query(TrainingWorkbookImportRow).filter(
            TrainingWorkbookImportRow.job_id == job.id,
            TrainingWorkbookImportRow.id.in_([decision.row_id for decision in payload.decisions] or [""]),
        ).all()
    }
    for decision in payload.decisions:
        row = rows_by_id.get(decision.row_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Decision row {decision.row_id} does not belong to this import.")
        selected = decision.decision.upper()
        if row.decision_options and selected not in {str(option).upper() for option in row.decision_options}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Decision {selected} is not valid for row {row.source_row}.")
        row.decision = selected
        row.updated_at = utcnow()
        db.add(row)
    db.commit()

    unresolved = db.query(TrainingWorkbookImportRow).filter(
        TrainingWorkbookImportRow.job_id == job.id,
        TrainingWorkbookImportRow.decision_required.is_(True),
        TrainingWorkbookImportRow.decision.is_(None),
    ).count()
    if unresolved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{unresolved} personnel or conflict review decision(s) are still required.")

    job.status = "QUEUED_COMMIT"
    job.stage = "QUEUED_COMMIT"
    job.actor_user_id = current_user.id
    job.completed_at = None
    job.error_message = None
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(commit_workbook_import, job.id, force_reimport=payload.force_reimport)
    return _job_read(db, job)


@router.post("/{job_id}/cancel", response_model=TrainingWorkbookImportJobRead)
def cancel_import(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_editor),
) -> TrainingWorkbookImportJobRead:
    job = _job_for_user(db, current_user, job_id)
    if job.status in {"COMPLETED", "CANCELLED"}:
        return _job_read(db, job)
    job.cancel_requested = True
    if job.status in {"QUEUED", "PREVIEW_READY", "REVIEW_REQUIRED", "FAILED"}:
        job.status = "CANCELLED"
        job.stage = "CANCELLED"
        job.completed_at = utcnow()
    db.add(job)
    db.commit()
    db.refresh(job)
    return _job_read(db, job)


@router.get("/users/{user_id}/licences", response_model=list[PersonnelLicenceRead])
def list_personnel_licences(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> list[PersonnelLicenceRead]:
    user_query = db.query(account_models.User).filter(account_models.User.id == user_id)
    if not current_user.is_superuser:
        user_query = user_query.filter(account_models.User.amo_id == current_user.amo_id)
    user = user_query.first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personnel user not found.")
    rows = db.query(PersonnelLicence).filter(PersonnelLicence.amo_id == user.amo_id, PersonnelLicence.user_id == user.id).order_by(PersonnelLicence.is_primary.desc(), PersonnelLicence.authority.asc()).all()
    return [PersonnelLicenceRead.model_validate(item) for item in rows]


@router.get("/role-groups", response_model=list[TrainingRoleGroupRead])
def list_role_groups(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> list[TrainingRoleGroupRead]:
    rows = db.query(TrainingRoleGroup).filter(TrainingRoleGroup.amo_id == current_user.amo_id, TrainingRoleGroup.is_active.is_(True)).order_by(TrainingRoleGroup.code.asc()).all()
    return [TrainingRoleGroupRead.model_validate(item) for item in rows]


@router.get("/role-rules", response_model=list[TrainingCourseRoleRuleRead])
def list_role_rules(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> list[TrainingCourseRoleRuleRead]:
    rows = db.query(TrainingCourseRoleRule, TrainingRoleGroup, __import__("amodb.apps.training.models", fromlist=["TrainingCourse"]).TrainingCourse).join(TrainingRoleGroup, TrainingCourseRoleRule.role_group_id == TrainingRoleGroup.id).join(__import__("amodb.apps.training.models", fromlist=["TrainingCourse"]).TrainingCourse, TrainingCourseRoleRule.course_id == __import__("amodb.apps.training.models", fromlist=["TrainingCourse"]).TrainingCourse.id).filter(TrainingCourseRoleRule.amo_id == current_user.amo_id, TrainingCourseRoleRule.is_active.is_(True)).all()
    return [TrainingCourseRoleRuleRead(id=rule.id, course_id=rule.course_id, course_code=course.course_id, course_name=course.course_name, role_group_id=rule.role_group_id, role_group_code=group.code, is_required=rule.is_required, requirement_type=rule.requirement_type, notes=rule.notes, is_active=rule.is_active) for rule, group, course in rows]


@router.get("/people/{user_id}/roles", response_model=list[TrainingPersonRoleRead])
def list_person_roles(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> list[TrainingPersonRoleRead]:
    user = db.query(account_models.User).filter(account_models.User.id == user_id, account_models.User.amo_id == current_user.amo_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personnel user not found.")
    rows = db.query(TrainingPersonRole, TrainingRoleGroup).join(TrainingRoleGroup, TrainingPersonRole.role_group_id == TrainingRoleGroup.id).filter(TrainingPersonRole.amo_id == current_user.amo_id, TrainingPersonRole.user_id == user.id, TrainingPersonRole.is_active.is_(True)).all()
    return [TrainingPersonRoleRead(id=assignment.id, person_id=assignment.person_id, personnel_profile_id=assignment.personnel_profile_id, user_id=assignment.user_id, role_group_id=assignment.role_group_id, role_group_code=group.code, department=assignment.department, position=assignment.position, notes=assignment.notes, is_active=assignment.is_active) for assignment, group in rows]
