from pathlib import Path
import re

path = Path("backend/amodb/apps/training/workbook_router.py")
text = path.read_text(encoding="utf-8")


def one(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count}")
    text = text.replace(old, new, 1)


def regex_one(pattern: str, replacement: str, label: str) -> None:
    global text
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count}")


one("import hashlib\nimport os\nimport re\n", "import hashlib\nfrom io import BytesIO\nimport os\nimport re\nfrom zipfile import BadZipFile, LargeZipFile, ZipFile\n", "archive imports")
one("from sqlalchemy import or_\n", "from sqlalchemy import or_\nfrom sqlalchemy.exc import IntegrityError\n", "integrity import")
one(
    '_IMPORT_DIR = Path(os.getenv("TRAINING_UPLOAD_DIR", "uploads/training")).resolve() / "workbook-imports"\n_IMPORT_DIR.mkdir(parents=True, exist_ok=True)\n_MAX_BYTES = int(os.getenv("TRAINING_WORKBOOK_MAX_UPLOAD_BYTES", str(40 * 1024 * 1024)))\n',
    '_IMPORT_DIR = Path(os.getenv("TRAINING_UPLOAD_DIR", "uploads/training")).resolve() / "workbook-imports"\n_MAX_BYTES = int(os.getenv("TRAINING_WORKBOOK_MAX_UPLOAD_BYTES", str(40 * 1024 * 1024)))\n_MAX_UNCOMPRESSED_BYTES = int(os.getenv("TRAINING_WORKBOOK_MAX_UNCOMPRESSED_BYTES", str(256 * 1024 * 1024)))\n',
    "upload limits",
)

validator = '''

def _validate_workbook_archive(content: bytes) -> None:
    """Reject malformed, encrypted, and decompression-bomb workbook archives."""
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            if not any(item.filename == "[Content_Types].xml" for item in members):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The file is not a valid Office workbook archive.")
            if any(item.flag_bits & 0x1 for item in members):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Encrypted workbooks cannot be imported.")
            expanded_size = sum(max(0, item.file_size) for item in members)
            if _MAX_UNCOMPRESSED_BYTES and expanded_size > _MAX_UNCOMPRESSED_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Workbook expands beyond the safe processing limit.")
    except HTTPException:
        raise
    except (BadZipFile, LargeZipFile, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is not a readable Excel workbook.") from exc
'''
one("\n\ndef _editor(current_user: account_models.User = Depends(get_current_active_user)) -> account_models.User:\n", validator + "\n\ndef _editor(current_user: account_models.User = Depends(get_current_active_user)) -> account_models.User:\n", "archive validator")

one(
    'def _job_for_user(db: Session, current_user: account_models.User, job_id: str) -> TrainingWorkbookImportJob:\n    query = db.query(TrainingWorkbookImportJob).filter(TrainingWorkbookImportJob.id == job_id)\n',
    'def _job_for_user(db: Session, current_user: account_models.User, job_id: str, *, for_update: bool = False) -> TrainingWorkbookImportJob:\n    query = db.query(TrainingWorkbookImportJob).filter(TrainingWorkbookImportJob.id == job_id)\n',
    "job lock signature",
)
one(
    '    if not current_user.is_superuser:\n        query = query.filter(TrainingWorkbookImportJob.amo_id == current_user.amo_id)\n    job = query.first()\n',
    '    if not current_user.is_superuser:\n        query = query.filter(TrainingWorkbookImportJob.amo_id == current_user.amo_id)\n    if for_update:\n        query = query.with_for_update()\n    job = query.first()\n',
    "job row lock",
)
one(
    '    if _MAX_BYTES and len(content) > _MAX_BYTES:\n        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"Workbook exceeds the {_MAX_BYTES // (1024 * 1024)} MB import limit.")\n\n    sha = hashlib.sha256(content).hexdigest()\n',
    '    if _MAX_BYTES and len(content) > _MAX_BYTES:\n        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"Workbook exceeds the {_MAX_BYTES // (1024 * 1024)} MB import limit.")\n    _validate_workbook_archive(content)\n\n    sha = hashlib.sha256(content).hexdigest()\n',
    "archive validation call",
)
one(
    '    if existing_key:\n        return _job_read(db, existing_key)\n',
    '    if existing_key:\n        if existing_key.file_sha256 != sha:\n            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This idempotency key is already bound to a different workbook.")\n        return _job_read(db, existing_key)\n',
    "idempotency content binding",
)
one(
    '    db.add(job)\n    db.commit()\n    db.refresh(job)\n    background_tasks.add_task(process_workbook_preview, job.id)\n',
    '    db.add(job)\n    try:\n        db.commit()\n    except IntegrityError as exc:\n        db.rollback()\n        raced = db.query(TrainingWorkbookImportJob).filter(\n            TrainingWorkbookImportJob.amo_id == current_user.amo_id,\n            TrainingWorkbookImportJob.idempotency_key == key,\n        ).first()\n        if not raced or raced.file_sha256 != sha:\n            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The workbook import could not claim its idempotency key.") from exc\n        return _job_read(db, raced)\n    db.refresh(job)\n    background_tasks.add_task(process_workbook_preview, job.id)\n',
    "idempotency race",
)

commit_function = '''@router.post("/{job_id}/commit", response_model=TrainingWorkbookImportJobRead, status_code=status.HTTP_202_ACCEPTED)
def commit_import(
    job_id: str,
    payload: WorkbookImportCommitRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_editor),
) -> TrainingWorkbookImportJobRead:
    # Lock the job while decisions are saved and the worker is claimed.
    job = _job_for_user(db, current_user, job_id, for_update=True)
    if job.status not in {"PREVIEW_READY", "REVIEW_REQUIRED", "FAILED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Import is currently {job.status.lower()} and cannot be committed.")

    decision_ids = [decision.row_id for decision in payload.decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each review row may be decided only once per request.")
    rows_by_id = {
        item.id: item
        for item in db.query(TrainingWorkbookImportRow).filter(
            TrainingWorkbookImportRow.job_id == job.id,
            TrainingWorkbookImportRow.id.in_(decision_ids or [""]),
        ).all()
    }
    for decision in payload.decisions:
        row = rows_by_id.get(decision.row_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Decision row {decision.row_id} does not belong to this import.")
        if not row.decision_required:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Row {row.source_row} does not accept a review decision.")
        selected = decision.decision.upper()
        options = {str(option).upper() for option in (row.decision_options or [])}
        if not options or selected not in options:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Decision {selected} is not valid for row {row.source_row}.")
        row.decision = selected
        row.updated_at = utcnow()
        db.add(row)
    db.flush()

    unresolved = db.query(TrainingWorkbookImportRow).filter(
        TrainingWorkbookImportRow.job_id == job.id,
        TrainingWorkbookImportRow.decision_required.is_(True),
        TrainingWorkbookImportRow.decision.is_(None),
    ).count()
    if unresolved:
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{unresolved} personnel or conflict review decision(s) are still required.")

    job.status = "QUEUED_COMMIT"
    job.stage = "QUEUED_COMMIT"
    job.actor_user_id = current_user.id
    job.cancel_requested = False
    job.completed_at = None
    job.error_message = None
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(commit_workbook_import, job.id, force_reimport=payload.force_reimport)
    return _job_read(db, job)


'''
regex_one(r'@router\.post\("/\{job_id\}/commit".*?\n\n(?=@router\.post\("/\{job_id\}/cancel")', commit_function, "atomic commit endpoint")

cancel_function = '''@router.post("/{job_id}/cancel", response_model=TrainingWorkbookImportJobRead)
def cancel_import(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_editor),
) -> TrainingWorkbookImportJobRead:
    job = _job_for_user(db, current_user, job_id, for_update=True)
    if job.status in {"COMPLETED", "CANCELLED"}:
        return _job_read(db, job)
    job.cancel_requested = True
    if job.status in {"QUEUED", "QUEUED_COMMIT", "PREVIEW_READY", "REVIEW_REQUIRED", "FAILED"}:
        job.status = "CANCELLED"
        job.stage = "CANCELLED"
        job.completed_at = utcnow()
    db.add(job)
    db.commit()
    db.refresh(job)
    return _job_read(db, job)


'''
regex_one(r'@router\.post\("/\{job_id\}/cancel".*?\n\n(?=@router\.get\("/users/\{user_id\}/licences")', cancel_function, "locked cancel endpoint")

path.write_text(text, encoding="utf-8")
