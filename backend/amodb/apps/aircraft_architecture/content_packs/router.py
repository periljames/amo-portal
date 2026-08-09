from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models, schemas, services

router = APIRouter(prefix="/content-packs", tags=["aircraft content packs"])


@router.post("/bootstrap", response_model=list[schemas.ContentPackRead])
def bootstrap_packs(
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return services.bootstrap_source_intake_packs(db, user=user)


@router.get("", response_model=list[schemas.ContentPackRead])
def list_packs(
    manufacturer: str | None = None,
    family: str | None = None,
    series: str | None = None,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    query = db.query(models.AircraftContentPack)
    if manufacturer:
        query = query.filter(models.AircraftContentPack.manufacturer == manufacturer)
    if family:
        query = query.filter(models.AircraftContentPack.family == family)
    if series:
        query = query.filter(models.AircraftContentPack.series == series)
    return query.order_by(
        models.AircraftContentPack.manufacturer,
        models.AircraftContentPack.family,
        models.AircraftContentPack.series,
        models.AircraftContentPack.code,
    ).all()


# ---------------------------------------------------------------------------
# OEM technical-data registry. Static paths stay ahead of /{pack_id} routes.
# ---------------------------------------------------------------------------


@router.get("/oem-publications", response_model=list[schemas.OemPublicationRead])
def list_oem_publications(
    manufacturer: str | None = None,
    family: str | None = None,
    series: str | None = None,
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
    return query.order_by(
        models.AircraftOemPublication.manufacturer,
        models.AircraftOemPublication.family,
        models.AircraftOemPublication.series,
        models.AircraftOemPublication.publication_code,
    ).all()


@router.post("/oem-publications", response_model=schemas.OemPublicationRead, status_code=201)
def create_oem_publication(
    payload: schemas.OemPublicationCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return services.create_oem_publication(db, payload=payload, user=user)


@router.get(
    "/oem-publications/{publication_id}/revisions",
    response_model=list[schemas.OemPublicationRevisionRead],
)
def list_oem_publication_revisions(
    publication_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    if not db.get(models.AircraftOemPublication, publication_id):
        raise HTTPException(status_code=404, detail="OEM publication not found")
    return db.query(models.AircraftOemPublicationRevision).filter(
        models.AircraftOemPublicationRevision.publication_id == publication_id
    ).order_by(
        models.AircraftOemPublicationRevision.effective_date.desc().nullslast(),
        models.AircraftOemPublicationRevision.created_at.desc(),
    ).all()


@router.post(
    "/oem-publications/{publication_id}/revisions",
    response_model=schemas.OemPublicationRevisionRead,
    status_code=201,
)
def submit_oem_publication_revision(
    publication_id: str,
    payload: schemas.OemPublicationRevisionCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    publication = db.get(models.AircraftOemPublication, publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="OEM publication not found")
    return services.submit_oem_publication_revision(
        db,
        publication=publication,
        payload=payload,
        user=user,
    )


@router.post(
    "/oem-publication-revisions/{revision_id}/decision",
    response_model=schemas.OemPublicationRevisionRead,
)
def decide_oem_publication_revision(
    revision_id: str,
    payload: schemas.OemPublicationRevisionDecision,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    revision = db.get(models.AircraftOemPublicationRevision, revision_id)
    if not revision:
        raise HTTPException(status_code=404, detail="OEM publication revision not found")
    return services.decide_oem_publication_revision(
        db,
        revision=revision,
        payload=payload,
        user=user,
    )


@router.get(
    "/oem-publication-revisions/{revision_id}/temporary-revisions",
    response_model=list[schemas.OemTemporaryRevisionRead],
)
def list_temporary_revisions(
    revision_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    if not db.get(models.AircraftOemPublicationRevision, revision_id):
        raise HTTPException(status_code=404, detail="OEM publication revision not found")
    return db.query(models.AircraftOemTemporaryRevision).filter(
        models.AircraftOemTemporaryRevision.publication_revision_id == revision_id
    ).order_by(
        models.AircraftOemTemporaryRevision.issue_date.desc().nullslast(),
        models.AircraftOemTemporaryRevision.created_at.desc(),
    ).all()


@router.post(
    "/oem-publication-revisions/{revision_id}/temporary-revisions",
    response_model=schemas.OemTemporaryRevisionRead,
    status_code=201,
)
def create_temporary_revision(
    revision_id: str,
    payload: schemas.OemTemporaryRevisionCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    revision = db.get(models.AircraftOemPublicationRevision, revision_id)
    if not revision:
        raise HTTPException(status_code=404, detail="OEM publication revision not found")
    return services.create_temporary_revision(
        db,
        publication_revision=revision,
        payload=payload,
        user=user,
    )


@router.post(
    "/oem-temporary-revisions/{temporary_revision_id}/decision",
    response_model=schemas.OemTemporaryRevisionRead,
)
def decide_temporary_revision(
    temporary_revision_id: str,
    payload: schemas.OemTemporaryRevisionDecision,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    row = db.get(models.AircraftOemTemporaryRevision, temporary_revision_id)
    if not row:
        raise HTTPException(status_code=404, detail="OEM temporary revision not found")
    return services.decide_temporary_revision(db, temporary_revision=row, payload=payload, user=user)


@router.get(
    "/oem-publications/{publication_id}/watches",
    response_model=list[schemas.OemSourceWatchRead],
)
def list_source_watches(
    publication_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    if not db.get(models.AircraftOemPublication, publication_id):
        raise HTTPException(status_code=404, detail="OEM publication not found")
    return db.query(models.AircraftOemSourceWatch).filter(
        models.AircraftOemSourceWatch.publication_id == publication_id
    ).order_by(models.AircraftOemSourceWatch.channel_type, models.AircraftOemSourceWatch.reference).all()


@router.post(
    "/oem-publications/{publication_id}/watches",
    response_model=schemas.OemSourceWatchRead,
    status_code=201,
)
def create_source_watch(
    publication_id: str,
    payload: schemas.OemSourceWatchCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    publication = db.get(models.AircraftOemPublication, publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="OEM publication not found")
    return services.create_source_watch(db, publication=publication, payload=payload, user=user)


@router.post(
    "/oem-source-watches/{watch_id}/check",
    response_model=schemas.OemSourceWatchRead,
)
def record_source_watch_check(
    watch_id: str,
    payload: schemas.OemSourceWatchCheck,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    watch = db.get(models.AircraftOemSourceWatch, watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="OEM source watch not found")
    return services.record_source_watch_check(db, watch=watch, payload=payload, user=user)


@router.get("/oem-currentness", response_model=list[schemas.OemPublicationCurrentnessRead])
def list_oem_currentness(
    family: str | None = None,
    series: str | None = None,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    query = db.query(models.AircraftOemPublication).filter(
        models.AircraftOemPublication.status == "ACTIVE"
    )
    if family:
        query = query.filter(models.AircraftOemPublication.family == family)
    if series:
        query = query.filter(models.AircraftOemPublication.series == series)
    publications = query.order_by(
        models.AircraftOemPublication.manufacturer,
        models.AircraftOemPublication.family,
        models.AircraftOemPublication.series,
        models.AircraftOemPublication.publication_code,
    ).all()
    return [services.publication_currentness(db, publication=row) for row in publications]


# ---------------------------------------------------------------------------
# Controlled content-pack revisions.
# ---------------------------------------------------------------------------


@router.get("/{pack_id}/revisions", response_model=list[schemas.ContentRevisionRead])
def list_pack_revisions(
    pack_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    if not db.get(models.AircraftContentPack, pack_id):
        raise HTTPException(status_code=404, detail="Content pack not found")
    return db.query(models.AircraftContentPackRevision).filter(
        models.AircraftContentPackRevision.pack_id == pack_id
    ).order_by(models.AircraftContentPackRevision.created_at.desc()).all()


@router.get("/revisions/{revision_id}", response_model=schemas.ContentRevisionDetailRead)
def get_content_revision(
    revision_id: str,
    task_limit: int = Query(default=10000, ge=1, le=50000),
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    revision = db.get(models.AircraftContentPackRevision, revision_id)
    if not revision:
        raise HTTPException(status_code=404, detail="Content-pack revision not found")
    # Relationships are select-in loaded, but bound very large source packs at the API edge.
    detail = schemas.ContentRevisionDetailRead.model_validate(revision)
    detail.tasks = detail.tasks[:task_limit]
    return detail


@router.get(
    "/revisions/{base_revision_id}/compare/{target_revision_id}",
    response_model=schemas.ContentRevisionDiffRead,
)
def compare_content_revisions(
    base_revision_id: str,
    target_revision_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    base = db.get(models.AircraftContentPackRevision, base_revision_id)
    target = db.get(models.AircraftContentPackRevision, target_revision_id)
    if not base or not target:
        raise HTTPException(status_code=404, detail="Content-pack revision not found")
    return services.compare_content_revisions(base, target)


@router.post("/{pack_id}/revisions", response_model=schemas.ContentRevisionRead, status_code=201)
def create_revision(
    pack_id: str,
    payload: schemas.ContentRevisionCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    pack = db.get(models.AircraftContentPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Content pack not found")
    return services.create_revision(db, pack=pack, payload=payload, user=user)


@router.post("/revisions/{revision_id}/publish", response_model=schemas.ContentRevisionRead)
def publish_revision(
    revision_id: str,
    payload: schemas.PublishContentRevision,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    revision = db.get(models.AircraftContentPackRevision, revision_id)
    if not revision:
        raise HTTPException(status_code=404, detail="Content-pack revision not found")
    return services.publish_revision(
        db,
        revision=revision,
        expected_content_hash=payload.expected_content_hash,
        user=user,
    )
