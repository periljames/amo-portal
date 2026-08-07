from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import (
    backend_queries,
    backend_schemas,
    backend_services,
    governance,
    ingestion,
    models,
    schemas,
)


router = APIRouter(
    prefix="/content-packs/governance",
    tags=["aircraft OEM backend governance"],
)


class SourceWatchActivation(BaseModel):
    is_active: bool
    decision_note: str = Field(min_length=1, max_length=4000)


def _publication(db: Session, publication_id: str) -> models.AircraftOemPublication:
    row = db.get(models.AircraftOemPublication, publication_id)
    if not row:
        raise HTTPException(status_code=404, detail="OEM publication not found")
    return row


def _revision(db: Session, revision_id: str) -> models.AircraftContentPackRevision:
    row = db.get(models.AircraftContentPackRevision, revision_id)
    if not row:
        raise HTTPException(status_code=404, detail="Content-pack revision not found")
    return row


def _page(total: int, offset: int, limit: int, items: list[dict[str, Any]]):
    return backend_schemas.PageRead(
        total=total,
        offset=offset,
        limit=limit,
        items=items,
    )


@router.get(
    "/oem-currentness",
    response_model=list[backend_schemas.OemPublicationGovernanceCurrentnessRead],
)
def list_governed_currentness(
    manufacturer: str | None = None,
    family: str | None = None,
    series: str | None = None,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    query = db.query(models.AircraftOemPublication).filter(
        models.AircraftOemPublication.status == "ACTIVE"
    )
    if manufacturer:
        query = query.filter(models.AircraftOemPublication.manufacturer == manufacturer)
    if family:
        query = query.filter(models.AircraftOemPublication.family == family)
    if series:
        query = query.filter(models.AircraftOemPublication.series == series)
    rows = query.order_by(
        models.AircraftOemPublication.manufacturer,
        models.AircraftOemPublication.family,
        models.AircraftOemPublication.series,
        models.AircraftOemPublication.publication_code,
    ).all()
    return [
        governance.governed_publication_currentness(db, publication=row)
        for row in rows
    ]


@router.get(
    "/publications/{publication_id}/currentness",
    response_model=backend_schemas.OemPublicationGovernanceCurrentnessRead,
)
def get_governed_currentness(
    publication_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    return governance.governed_publication_currentness(
        db,
        publication=_publication(db, publication_id),
    )


@router.patch(
    "/publications/{publication_id}/status",
    response_model=schemas.OemPublicationRead,
)
def set_publication_status(
    publication_id: str,
    payload: backend_schemas.PublicationStatusDecision,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return governance.set_publication_status(
        db,
        publication=_publication(db, publication_id),
        payload=payload,
        user=user,
    )


@router.post(
    "/temporary-revisions/{temporary_revision_id}/decision",
    response_model=schemas.OemTemporaryRevisionRead,
)
def decide_temporary_revision(
    temporary_revision_id: str,
    payload: backend_schemas.OemTemporaryRevisionGovernanceDecision,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    row = db.get(models.AircraftOemTemporaryRevision, temporary_revision_id)
    if not row:
        raise HTTPException(status_code=404, detail="OEM Temporary Revision not found")
    return governance.governed_temporary_revision_decision(
        db,
        temporary_revision=row,
        payload=payload,
        user=user,
    )


@router.get(
    "/publications/{publication_id}/watches",
    response_model=list[backend_schemas.OemSourceWatchGovernanceRead],
)
def list_governed_source_watches(
    publication_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    publication = _publication(db, publication_id)
    rows = (
        db.query(models.AircraftOemSourceWatch)
        .filter(models.AircraftOemSourceWatch.publication_id == publication.id)
        .order_by(
            models.AircraftOemSourceWatch.channel_type,
            models.AircraftOemSourceWatch.reference,
        )
        .all()
    )
    return [governance.governed_watch_read(row) for row in rows]


@router.post(
    "/publications/{publication_id}/watches",
    response_model=backend_schemas.OemSourceWatchGovernanceRead,
    status_code=201,
)
def create_governed_source_watch(
    publication_id: str,
    payload: backend_schemas.OemSourceWatchGovernanceCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    row = governance.create_governed_source_watch(
        db,
        publication=_publication(db, publication_id),
        payload=payload,
        user=user,
    )
    return governance.governed_watch_read(row)


@router.post(
    "/source-watches/{watch_id}/checks",
    response_model=backend_schemas.OemSourceWatchGovernanceRead,
)
def record_governed_source_watch_check(
    watch_id: str,
    payload: backend_schemas.OemSourceWatchGovernanceCheck,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    watch = db.get(models.AircraftOemSourceWatch, watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="OEM source watch not found")
    row = governance.record_governed_source_watch_check(
        db,
        watch=watch,
        payload=payload,
        user=user,
    )
    return governance.governed_watch_read(row)


@router.patch(
    "/source-watches/{watch_id}/activation",
    response_model=backend_schemas.OemSourceWatchGovernanceRead,
)
def set_source_watch_activation(
    watch_id: str,
    payload: SourceWatchActivation,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    governance.require_platform_human(user)
    watch = (
        db.query(models.AircraftOemSourceWatch)
        .filter(models.AircraftOemSourceWatch.id == watch_id)
        .with_for_update(of=models.AircraftOemSourceWatch)
        .first()
    )
    if not watch:
        raise HTTPException(status_code=404, detail="OEM source watch not found")
    before = watch.is_active
    watch.is_active = payload.is_active
    db.add(watch)
    governance._audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_SOURCE_WATCH",
        entity_id=watch.id,
        action="ACTIVATE" if payload.is_active else "DEACTIVATE",
        before={"is_active": before},
        after={"is_active": watch.is_active},
        metadata={"decision_note": payload.decision_note},
        critical=True,
    )
    db.commit()
    db.refresh(watch)
    return governance.governed_watch_read(watch)


@router.get("/revisions/{revision_id}/overview", response_model=dict[str, Any])
def revision_overview(
    revision_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    result = backend_queries.revision_overview(db, revision_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Content-pack revision not found")
    return result


@router.get(
    "/revisions/{revision_id}/{entity}",
    response_model=backend_schemas.PageRead,
)
def page_revision_entities(
    revision_id: str,
    entity: Literal["sources", "positions", "components", "tasks", "resources"],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=250, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    if backend_queries.revision_without_collections(db, revision_id) is None:
        raise HTTPException(status_code=404, detail="Content-pack revision not found")
    if entity == "sources":
        total, rows = backend_queries.page_revision_sources(
            db,
            revision_id=revision_id,
            offset=offset,
            limit=limit,
        )
    else:
        total, rows = backend_queries.page_revision_entities(
            db,
            revision_id=revision_id,
            entity=entity,
            offset=offset,
            limit=limit,
        )
    return _page(total, offset, limit, rows)


@router.get(
    "/revisions/{base_revision_id}/compare/{target_revision_id}",
    response_model=backend_schemas.ContentRevisionExtendedDiffRead,
)
def compare_content_revisions(
    base_revision_id: str,
    target_revision_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    base = _revision(db, base_revision_id)
    target = _revision(db, target_revision_id)
    return governance.extended_revision_diff(base, target)


@router.post(
    "/revisions/{revision_id}/withdraw",
    response_model=schemas.ContentRevisionRead,
)
def withdraw_content_revision(
    revision_id: str,
    payload: backend_schemas.ContentRevisionWithdraw,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return governance.withdraw_content_revision(
        db,
        revision=_revision(db, revision_id),
        payload=payload,
        user=user,
    )


@router.post(
    "/intakes",
    response_model=backend_schemas.OemSourceIntakeRead,
    status_code=201,
)
async def stage_oem_source_intake(
    publication_id: str = Form(...),
    publication_revision_id: str = Form(...),
    pack_id: str = Form(...),
    temporary_revision_id: str | None = Form(default=None),
    storage_locator: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    content = await file.read(ingestion.MAX_SOURCE_BYTES + 1)
    if len(content) > ingestion.MAX_SOURCE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"OEM source workbook exceeds the {ingestion.MAX_SOURCE_BYTES // (1024 * 1024)} MB intake limit"
            ),
        )
    binding = backend_schemas.IntakeSourceBinding(
        publication_id=publication_id,
        publication_revision_id=publication_revision_id,
        temporary_revision_id=temporary_revision_id,
        pack_id=pack_id,
        storage_locator=storage_locator,
    )
    return backend_services.stage_intake(
        db,
        filename=file.filename or "source-workbook",
        content=content,
        binding=binding,
        user=user,
    )


@router.get("/intakes", response_model=backend_schemas.PageRead)
def list_oem_source_intakes(
    status: Literal[
        "STAGED",
        "VALIDATED",
        "APPROVED",
        "MATERIALIZED",
        "REJECTED",
        "FAILED",
    ]
    | None = None,
    publication_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    total, rows = backend_services.list_intakes(
        db,
        user=user,
        status=status,
        publication_id=publication_id,
        offset=offset,
        limit=limit,
    )
    items = [
        backend_schemas.OemSourceIntakeRead.model_validate(row).model_dump(mode="json")
        for row in rows
    ]
    return _page(total, offset, limit, items)


@router.get(
    "/intakes/{intake_id}",
    response_model=backend_schemas.OemSourceIntakeRead,
)
def get_oem_source_intake(
    intake_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return backend_services.get_intake(
        db,
        intake_id=intake_id,
        user=user,
    )


@router.get(
    "/intakes/{intake_id}/rows",
    response_model=backend_schemas.PageRead,
)
def list_oem_source_intake_rows(
    intake_id: str,
    status: Literal["VALID", "REVIEW_REQUIRED", "INVALID", "IGNORED"] | None = None,
    row_kind: Literal["TASK", "RESOURCE", "UNMAPPED", "IGNORED"] | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=250, ge=1, le=2000),
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    total, rows = backend_services.list_intake_rows(
        db,
        intake_id=intake_id,
        user=user,
        status=status,
        row_kind=row_kind,
        offset=offset,
        limit=limit,
    )
    items = [
        backend_schemas.OemSourceIntakeRowRead.model_validate(row).model_dump(mode="json")
        for row in rows
    ]
    return _page(total, offset, limit, items)


@router.post(
    "/intakes/{intake_id}/validate",
    response_model=backend_schemas.OemSourceIntakeValidateRead,
)
def validate_oem_source_intake(
    intake_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return backend_services.validate_intake(
        db,
        intake_id=intake_id,
        user=user,
    )


@router.post(
    "/intake-rows/{row_id}/resolve",
    response_model=backend_schemas.OemSourceIntakeRowRead,
)
def resolve_oem_source_intake_row(
    row_id: str,
    payload: backend_schemas.OemSourceIntakeRowResolution,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return backend_services.resolve_intake_row(
        db,
        row_id=row_id,
        payload=payload,
        user=user,
    )


@router.post(
    "/intakes/{intake_id}/approve",
    response_model=backend_schemas.OemSourceIntakeRead,
)
def approve_oem_source_intake(
    intake_id: str,
    payload: backend_schemas.OemSourceIntakeApproval,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return backend_services.approve_intake(
        db,
        intake_id=intake_id,
        payload=payload,
        user=user,
    )


@router.post(
    "/intakes/{intake_id}/materialize",
    response_model=schemas.ContentRevisionRead,
    status_code=201,
)
def materialize_oem_source_intake(
    intake_id: str,
    payload: backend_schemas.OemSourceIntakeMaterialize,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return backend_services.materialize_intake(
        db,
        intake_id=intake_id,
        payload=payload,
        user=user,
    )
