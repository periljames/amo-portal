from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models, schemas, services

router = APIRouter(prefix="/programmes", tags=["tenant maintenance programmes"])


def _amo_id(user: account_models.User) -> str:
    value = getattr(user, "amo_id", None)
    if not value:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return str(value)


@router.post("", response_model=schemas.ProgrammeRead, status_code=201)
def create_programme(
    payload: schemas.ProgrammeCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo_id(user)
    duplicate = db.query(models.TenantMaintenanceProgramme.id).filter(
        models.TenantMaintenanceProgramme.amo_id == amo_id,
        models.TenantMaintenanceProgramme.code == payload.code,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Programme code already exists")
    row = models.TenantMaintenanceProgramme(
        amo_id=amo_id,
        **payload.model_dump(),
        created_by_user_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/{programme_id}/revisions", response_model=schemas.RevisionRead, status_code=201)
def create_revision(
    programme_id: str,
    payload: schemas.RevisionCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    programme = db.get(models.TenantMaintenanceProgramme, programme_id)
    if not programme or programme.amo_id != _amo_id(user):
        raise HTTPException(status_code=404, detail="Programme not found")
    task_dicts = [task.model_dump() for task in payload.tasks]
    content_hash = services.programme_revision_hash(
        programme.code,
        payload.revision_code,
        payload.aircraft_type_revision_id,
        payload.effectivity_rule_version_id,
        payload.source_reference,
        payload.source_revision,
        task_dicts,
    )
    values = payload.model_dump(exclude={"tasks"})
    if values.get("source_checksum_sha256"):
        values["source_checksum_sha256"] = values["source_checksum_sha256"].lower()
    revision = models.TenantProgrammeRevision(
        programme_id=programme.id,
        **values,
        content_hash=content_hash,
        created_by_user_id=user.id,
    )
    db.add(revision)
    db.flush()
    for task in task_dicts:
        db.add(models.TenantProgrammeTask(revision_id=revision.id, **task))
    db.commit()
    db.refresh(revision)
    return revision


@router.post("/revisions/{revision_id}/publish", response_model=schemas.RevisionRead)
def publish_revision(
    revision_id: str,
    payload: schemas.PublishRequest,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    revision = db.get(models.TenantProgrammeRevision, revision_id)
    if not revision or revision.programme.amo_id != _amo_id(user):
        raise HTTPException(status_code=404, detail="Programme revision not found")
    if revision.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Published programme revisions are immutable")
    if revision.content_hash != payload.expected_content_hash:
        raise HTTPException(status_code=409, detail="Programme content changed after review")
    current = db.query(models.TenantProgrammeRevision).filter(
        models.TenantProgrammeRevision.programme_id == revision.programme_id,
        models.TenantProgrammeRevision.status == "PUBLISHED",
    ).with_for_update().all()
    for previous in current:
        previous.status = "SUPERSEDED"
        db.add(previous)
    revision.status = "PUBLISHED"
    revision.published_by_user_id = user.id
    revision.published_at = datetime.now(timezone.utc)
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


@router.post("/upgrade-impact")
def upgrade_impact(
    payload: schemas.UpgradeImpactRequest,
    _: account_models.User = Depends(get_current_active_user),
):
    return services.build_upgrade_impact(payload.current_tasks, payload.proposed_tasks)
