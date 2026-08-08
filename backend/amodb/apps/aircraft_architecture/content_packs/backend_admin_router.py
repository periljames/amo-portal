from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import (
    backend_models,
    backend_schemas,
    governance,
    models,
    schemas,
    services as legacy_services,
)


router = APIRouter(
    prefix="/content-packs/governance",
    tags=["aircraft OEM backend governance"],
)


class IntakeRejectDecision(BaseModel):
    decision_note: str = Field(min_length=1, max_length=4000)


class PublicationPageItem(BaseModel):
    publication: schemas.OemPublicationRead
    currentness_status: str
    current_revision_id: str | None
    current_revision_code: str | None
    active_temporary_revision_count: int
    pending_temporary_revision_count: int
    source_watch_count: int


class PublicationRevisionPageItem(BaseModel):
    revision: schemas.OemPublicationRevisionRead
    temporary_revision_count: int
    active_temporary_revision_count: int
    content_source_reference_count: int


class SourceWatchDueItem(BaseModel):
    publication: schemas.OemPublicationRead
    watch: backend_schemas.OemSourceWatchGovernanceRead


class ContentSourceLineageItem(BaseModel):
    source: schemas.ContentSourceRead
    publication: schemas.OemPublicationRead | None
    publication_revision: schemas.OemPublicationRevisionRead | None
    temporary_revision: schemas.OemTemporaryRevisionRead | None
    source_intake: backend_schemas.OemSourceIntakeRead | None


def _page(total: int, offset: int, limit: int, items: list[dict[str, Any]]):
    return backend_schemas.PageRead(
        total=total,
        offset=offset,
        limit=limit,
        items=items,
    )


def _intake_scope(
    intake: backend_models.AircraftOemSourceIntake,
    user: account_models.User,
) -> None:
    governance.require_source_contributor(user)
    if bool(getattr(user, "is_superuser", False)):
        return
    if intake.submitted_by_amo_id != getattr(user, "amo_id", None):
        raise HTTPException(status_code=404, detail="OEM source intake not found")


@router.get("/publications", response_model=backend_schemas.PageRead)
def list_publication_registry(
    manufacturer: str | None = None,
    family: str | None = None,
    series: str | None = None,
    status: Literal["ACTIVE", "INACTIVE"] | None = None,
    currentness: Literal[
        "NO_CURRENT_REVISION",
        "CURRENT",
        "CANDIDATE_REVIEW_REQUIRED",
        "TEMPORARY_REVISION_REVIEW_REQUIRED",
        "TEMPORARY_REVISION_ACTIVE",
        "SOURCE_CHANGE_DETECTED",
        "SOURCE_CHECK_REQUIRED",
    ]
    | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    query = db.query(models.AircraftOemPublication)
    if manufacturer:
        query = query.filter(models.AircraftOemPublication.manufacturer == manufacturer)
    if family:
        query = query.filter(models.AircraftOemPublication.family == family)
    if series:
        query = query.filter(models.AircraftOemPublication.series == series)
    if status:
        query = query.filter(models.AircraftOemPublication.status == status)

    # Currentness is derived from revisions/TRs/watches and therefore cannot be
    # represented faithfully by a single denormalized database column. When it
    # is requested we scan the bounded registry query and paginate after the
    # derived filter rather than returning a false approximation.
    ordered = query.order_by(
        models.AircraftOemPublication.manufacturer,
        models.AircraftOemPublication.family,
        models.AircraftOemPublication.series,
        models.AircraftOemPublication.publication_code,
    )
    if currentness:
        rows = ordered.limit(5000).all()
        derived = [
            (row, governance.governed_publication_currentness(db, publication=row))
            for row in rows
        ]
        derived = [pair for pair in derived if pair[1].currentness_status == currentness]
        total = len(derived)
        page_rows = derived[offset : offset + limit]
    else:
        total = int(ordered.count())
        page_rows = [
            (row, governance.governed_publication_currentness(db, publication=row))
            for row in ordered.offset(offset).limit(limit).all()
        ]

    items: list[dict[str, Any]] = []
    for publication, governed in page_rows:
        item = PublicationPageItem(
            publication=governed.publication,
            currentness_status=governed.currentness_status,
            current_revision_id=(
                governed.current_revision.id if governed.current_revision else None
            ),
            current_revision_code=(
                governed.current_revision.revision_code if governed.current_revision else None
            ),
            active_temporary_revision_count=len(governed.active_temporary_revisions),
            pending_temporary_revision_count=len(governed.pending_temporary_revisions),
            source_watch_count=len(governed.governed_watches),
        )
        items.append(item.model_dump(mode="json"))
    return _page(total, offset, limit, items)


@router.get(
    "/publications/{publication_id}/revisions",
    response_model=backend_schemas.PageRead,
)
def list_publication_revisions(
    publication_id: str,
    status: Literal[
        "CANDIDATE",
        "VERIFIED",
        "CURRENT",
        "SUPERSEDED",
        "WITHDRAWN",
        "REJECTED",
    ]
    | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    publication = db.get(models.AircraftOemPublication, publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="OEM publication not found")
    query = db.query(models.AircraftOemPublicationRevision).filter(
        models.AircraftOemPublicationRevision.publication_id == publication.id
    )
    if status:
        query = query.filter(models.AircraftOemPublicationRevision.status == status)
    total = int(query.count())
    revisions = (
        query.order_by(
            models.AircraftOemPublicationRevision.effective_date.desc().nullslast(),
            models.AircraftOemPublicationRevision.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    items: list[dict[str, Any]] = []
    for revision in revisions:
        trs = revision.temporary_revisions
        source_reference_count = int(
            db.query(models.AircraftContentPackSource.id)
            .filter(
                models.AircraftContentPackSource.publication_revision_id == revision.id
            )
            .count()
        )
        items.append(
            PublicationRevisionPageItem(
                revision=schemas.OemPublicationRevisionRead.model_validate(revision),
                temporary_revision_count=len(trs),
                active_temporary_revision_count=sum(
                    1 for row in trs if row.status == "ACTIVE"
                ),
                content_source_reference_count=source_reference_count,
            ).model_dump(mode="json")
        )
    return _page(total, offset, limit, items)


@router.get("/source-watches/due", response_model=backend_schemas.PageRead)
def list_due_source_watches(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    # Source-watch cadence is controlled per watch in metadata. The registry is
    # expected to remain small; still cap the derived scan to avoid an unbounded
    # request if external watch channels grow unexpectedly.
    watches = (
        db.query(models.AircraftOemSourceWatch)
        .filter(models.AircraftOemSourceWatch.is_active.is_(True))
        .order_by(
            models.AircraftOemSourceWatch.last_checked_at.asc().nullsfirst(),
            models.AircraftOemSourceWatch.created_at.asc(),
        )
        .limit(5000)
        .all()
    )
    due = []
    now = datetime.now(timezone.utc)
    for watch in watches:
        governed = governance.governed_watch_read(watch, now=now)
        if governed.overdue or governed.last_result_code in {
            "CHANGE_DETECTED",
            "ERROR",
            "AUTH_REQUIRED",
            "UNAVAILABLE",
        }:
            due.append((watch, governed))
    total = len(due)
    page_rows = due[offset : offset + limit]
    items = [
        SourceWatchDueItem(
            publication=schemas.OemPublicationRead.model_validate(watch.publication),
            watch=governed,
        ).model_dump(mode="json")
        for watch, governed in page_rows
    ]
    return _page(total, offset, limit, items)


@router.post(
    "/intakes/{intake_id}/reject",
    response_model=backend_schemas.OemSourceIntakeRead,
)
def reject_oem_source_intake(
    intake_id: str,
    payload: IntakeRejectDecision,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    legacy_services._advisory_lock(db, f"aircraft-oem-intake-reject:{intake_id}")
    intake = (
        db.query(backend_models.AircraftOemSourceIntake)
        .filter(backend_models.AircraftOemSourceIntake.id == intake_id)
        .with_for_update(of=backend_models.AircraftOemSourceIntake)
        .first()
    )
    if not intake:
        raise HTTPException(status_code=404, detail="OEM source intake not found")
    _intake_scope(intake, user)
    if intake.status == "MATERIALIZED":
        raise HTTPException(
            status_code=409,
            detail="Materialized OEM source intake cannot be rejected; withdraw the materialized content revision instead",
        )
    if intake.status == "APPROVED" and not bool(getattr(user, "is_superuser", False)):
        raise HTTPException(
            status_code=403,
            detail="Platform superuser authority is required to reject an approved OEM source intake",
        )
    if intake.status == "REJECTED":
        return intake
    before = intake.status
    now = datetime.now(timezone.utc)
    summary = dict(intake.validation_summary_json or {})
    decisions = list(summary.get("lifecycle_decisions") or [])
    decisions.append(
        {
            "action": "REJECT",
            "note": payload.decision_note,
            "actor_user_id": user.id,
            "at": now.isoformat(),
        }
    )
    summary["lifecycle_decisions"] = decisions
    intake.validation_summary_json = summary
    intake.status = "REJECTED"
    db.add(intake)
    governance._audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_SOURCE_INTAKE",
        entity_id=intake.id,
        action="REJECT",
        before={"status": before},
        after={"status": "REJECTED"},
        metadata={"decision_note": payload.decision_note},
        critical=True,
    )
    db.commit()
    db.refresh(intake)
    return intake


@router.get(
    "/revisions/{revision_id}/lineage",
    response_model=list[ContentSourceLineageItem],
)
def get_content_source_lineage(
    revision_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    revision = db.get(models.AircraftContentPackRevision, revision_id)
    if not revision:
        raise HTTPException(status_code=404, detail="Content-pack revision not found")
    result: list[ContentSourceLineageItem] = []
    for source in revision.sources:
        publication_revision = (
            db.get(models.AircraftOemPublicationRevision, source.publication_revision_id)
            if source.publication_revision_id
            else None
        )
        publication = publication_revision.publication if publication_revision else None
        temporary = (
            db.get(models.AircraftOemTemporaryRevision, source.temporary_revision_id)
            if source.temporary_revision_id
            else None
        )
        intake = None
        intake_id = str((source.provenance_json or {}).get("source_intake_id") or "").strip()
        if intake_id:
            intake = db.get(backend_models.AircraftOemSourceIntake, intake_id)
        result.append(
            ContentSourceLineageItem(
                source=schemas.ContentSourceRead.model_validate(source),
                publication=(
                    schemas.OemPublicationRead.model_validate(publication)
                    if publication
                    else None
                ),
                publication_revision=(
                    schemas.OemPublicationRevisionRead.model_validate(publication_revision)
                    if publication_revision
                    else None
                ),
                temporary_revision=(
                    schemas.OemTemporaryRevisionRead.model_validate(temporary)
                    if temporary
                    else None
                ),
                source_intake=(
                    backend_schemas.OemSourceIntakeRead.model_validate(intake)
                    if intake
                    else None
                ),
            )
        )
    return result
