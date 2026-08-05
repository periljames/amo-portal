from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models, schemas, services

router = APIRouter(prefix="/imports", tags=["aircraft import staging"])


def _amo_id(user: account_models.User) -> str:
    value = getattr(user, "amo_id", None)
    if not value:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return str(value)


def _batch(db: Session, batch_id: str, user: account_models.User) -> models.AircraftImportBatch:
    row = db.get(models.AircraftImportBatch, batch_id)
    if not row or row.amo_id != _amo_id(user):
        raise HTTPException(status_code=404, detail="Import batch not found")
    return row


@router.post("/mapping-profiles", response_model=schemas.MappingProfileRead, status_code=201)
def create_mapping_profile(payload: schemas.MappingProfileCreate, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    amo_id = None if payload.scope == "GLOBAL" else _amo_id(user)
    if payload.scope == "GLOBAL" and not bool(getattr(user, "is_superuser", False)):
        raise HTTPException(status_code=403, detail="Only platform superusers may create global mapping profiles")
    duplicate = db.query(models.ImportMappingProfile.id).filter(models.ImportMappingProfile.amo_id == amo_id, models.ImportMappingProfile.code == payload.code).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Mapping profile code already exists in this scope")
    row = models.ImportMappingProfile(**payload.model_dump(exclude={"amo_id"}), amo_id=amo_id, created_by_user_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/mapping-profiles/{profile_id}/versions", response_model=schemas.MappingVersionRead, status_code=201)
def create_mapping_version(profile_id: str, payload: schemas.MappingVersionCreate, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    profile = db.get(models.ImportMappingProfile, profile_id)
    if not profile or (profile.amo_id and profile.amo_id != _amo_id(user)):
        raise HTTPException(status_code=404, detail="Mapping profile not found")
    fingerprint = services.header_fingerprint(payload.headers)
    content_hash = services.sha256_json({
        "profile_code": profile.code,
        "version_code": payload.version_code,
        "header_fingerprint": fingerprint,
        "mapping": payload.mapping_json,
        "parser_options": payload.parser_options_json,
    })
    row = models.ImportMappingProfileVersion(
        profile_id=profile.id,
        version_code=payload.version_code,
        header_fingerprint=fingerprint,
        mapping_json=payload.mapping_json,
        parser_options_json=payload.parser_options_json,
        content_hash=content_hash,
        created_by_user_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/mapping-versions/{version_id}/publish", response_model=schemas.MappingVersionRead)
def publish_mapping_version(version_id: str, payload: schemas.PublishMappingVersionRequest, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    version = db.get(models.ImportMappingProfileVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Mapping profile version not found")
    profile = version.profile
    if profile.amo_id and profile.amo_id != _amo_id(user):
        raise HTTPException(status_code=404, detail="Mapping profile version not found")
    if profile.scope == "GLOBAL" and not bool(getattr(user, "is_superuser", False)):
        raise HTTPException(status_code=403, detail="Only platform superusers may publish global mapping profiles")
    if version.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Published mapping profile versions are immutable")
    if payload.expected_content_hash != version.content_hash:
        raise HTTPException(status_code=409, detail="Mapping profile content changed after review")
    current = db.query(models.ImportMappingProfileVersion).filter(
        models.ImportMappingProfileVersion.profile_id == profile.id,
        models.ImportMappingProfileVersion.status == "PUBLISHED",
    ).with_for_update().all()
    for previous in current:
        previous.status = "SUPERSEDED"
        db.add(previous)
    version.status = "PUBLISHED"
    version.published_by_user_id = user.id
    version.published_at = datetime.now(timezone.utc)
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.post("/batches", response_model=schemas.BatchRead, status_code=201)
def create_batch(payload: schemas.BatchCreate, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    amo_id = _amo_id(user)
    datasets = [services.DatasetInput(item.dataset_kind, item.adapter_code, item.file_name, item.content_hash, tuple(item.headers), item.row_count) for item in payload.datasets]
    registry = services.default_adapter_registry()
    for item in datasets:
        registry.resolve(item.adapter_code)
    manifest_hash = services.batch_manifest_hash(payload.source_system, datasets)
    duplicate = db.query(models.AircraftImportBatch).filter(
        models.AircraftImportBatch.amo_id == amo_id,
        models.AircraftImportBatch.idempotency_key == payload.idempotency_key,
    ).first()
    if duplicate:
        if duplicate.manifest_hash != manifest_hash:
            raise HTTPException(status_code=409, detail="Idempotency key was reused with different content")
        return duplicate
    batch = models.AircraftImportBatch(
        amo_id=amo_id,
        source_system=payload.source_system.strip().upper(),
        idempotency_key=payload.idempotency_key,
        manifest_hash=manifest_hash,
        created_by_user_id=user.id,
    )
    db.add(batch)
    db.flush()
    for item in datasets:
        manifest = item.manifest()
        db.add(models.AircraftImportDataset(
            batch_id=batch.id,
            dataset_kind=manifest["dataset_kind"],
            adapter_code=manifest["adapter_code"],
            file_name=manifest["file_name"],
            content_hash=manifest["content_hash"],
            header_fingerprint=manifest["header_fingerprint"],
            row_count=manifest["row_count"],
        ))
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/datasets/{dataset_id}/rows", response_model=schemas.StagingRowRead, status_code=201)
def add_staging_row(dataset_id: str, payload: schemas.StagingRowCreate, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    dataset = db.get(models.AircraftImportDataset, dataset_id)
    if not dataset or dataset.batch.amo_id != _amo_id(user):
        raise HTTPException(status_code=404, detail="Import dataset not found")
    if dataset.batch.status != "STAGED":
        raise HTTPException(status_code=409, detail="Rows may only be added while the batch is STAGED")
    digest = services.row_hash(payload.source_json, payload.normalized_json)
    duplicate = db.query(models.AircraftImportStagingRow).filter(
        models.AircraftImportStagingRow.dataset_id == dataset.id,
        models.AircraftImportStagingRow.row_number == payload.row_number,
    ).first()
    if duplicate:
        if duplicate.row_hash != digest:
            raise HTTPException(status_code=409, detail="Row number was reused with different content")
        return duplicate
    row = models.AircraftImportStagingRow(
        dataset_id=dataset.id,
        row_hash=digest,
        **payload.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/batches/{batch_id}/issues", response_model=schemas.IssueRead, status_code=201)
def add_issue(batch_id: str, payload: schemas.IssueCreate, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    batch = _batch(db, batch_id, user)
    if batch.status not in {"STAGED", "VALIDATED", "RECONCILED"}:
        raise HTTPException(status_code=409, detail="Issues cannot be added after batch approval")
    if payload.dataset_id:
        dataset = db.get(models.AircraftImportDataset, payload.dataset_id)
        if not dataset or dataset.batch_id != batch.id:
            raise HTTPException(status_code=422, detail="Issue dataset does not belong to the batch")
    if payload.row_id:
        row = db.get(models.AircraftImportStagingRow, payload.row_id)
        if not row or row.dataset.batch_id != batch.id:
            raise HTTPException(status_code=422, detail="Issue row does not belong to the batch")
    issue = models.AircraftImportIssue(batch_id=batch.id, **payload.model_dump())
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


@router.post("/issues/{issue_id}/decisions", response_model=schemas.IssueRead)
def decide_issue(issue_id: str, payload: schemas.DecisionCreate, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    issue = db.get(models.AircraftImportIssue, issue_id)
    if not issue or issue.batch.amo_id != _amo_id(user):
        raise HTTPException(status_code=404, detail="Import issue not found")
    if issue.batch.status not in {"VALIDATED", "RECONCILED"}:
        raise HTTPException(status_code=409, detail="Issue decisions require a validated or reconciled batch")
    if payload.decision == "CORRECT" and not payload.correction_json:
        raise HTTPException(status_code=422, detail="CORRECT requires correction_json")
    db.add(models.AircraftImportDecision(
        issue_id=issue.id,
        decision=payload.decision,
        rationale=payload.rationale,
        correction_json=payload.correction_json,
        decided_by_user_id=user.id,
    ))
    issue.resolution_status = "WAIVED" if payload.decision == "WAIVE" else "RESOLVED"
    if issue.row_id:
        row = db.get(models.AircraftImportStagingRow, issue.row_id)
        if row:
            row.status = "RESOLVED" if payload.decision in {"ACCEPT", "CORRECT", "WAIVE"} else "INVALID"
            db.add(row)
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


@router.post("/batches/{batch_id}/transition", response_model=schemas.BatchRead)
def transition_batch(batch_id: str, payload: schemas.BatchTransitionRequest, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    batch = db.query(models.AircraftImportBatch).filter(
        models.AircraftImportBatch.id == batch_id,
        models.AircraftImportBatch.amo_id == _amo_id(user),
    ).with_for_update().first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")
    target = payload.target_status
    try:
        services.require_batch_transition(batch.status, target)
        if target == "APPROVED":
            open_errors = db.query(models.AircraftImportIssue.id).filter(
                models.AircraftImportIssue.batch_id == batch.id,
                models.AircraftImportIssue.severity == "ERROR",
                models.AircraftImportIssue.resolution_status == "OPEN",
            ).count()
            services.approval_preconditions(dataset_count=len(batch.datasets), open_error_count=open_errors)
            batch.approved_by_user_id = user.id
            batch.approved_at = datetime.now(timezone.utc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    batch.status = target
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch
