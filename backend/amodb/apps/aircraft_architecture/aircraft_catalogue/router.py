from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_db
from amodb.security import get_current_active_user
from amodb.apps.accounts import models as account_models

from . import models, schemas, services

router = APIRouter(prefix="/catalogue", tags=["aircraft type catalogue"])


def _write_user(current_user: account_models.User = Depends(get_current_active_user)) -> account_models.User:
    services.require_catalogue_writer(current_user)
    return current_user


@router.get("/families", response_model=list[schemas.FamilyRead])
def list_families(
    status_filter: str | None = Query(default="ACTIVE", alias="status"),
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    query = db.query(models.AircraftFamily).order_by(models.AircraftFamily.manufacturer, models.AircraftFamily.code)
    if status_filter:
        query = query.filter(models.AircraftFamily.status == status_filter.upper())
    return query.all()


@router.post("/families", response_model=schemas.FamilyRead, status_code=201)
def create_family(
    payload: schemas.FamilyCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_write_user),
):
    return services.create_family(db, payload, current_user.id)


@router.get("/types", response_model=list[schemas.TemplateRead])
def list_templates(
    family_id: str | None = None,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    query = db.query(models.AircraftTypeTemplate).order_by(models.AircraftTypeTemplate.manufacturer, models.AircraftTypeTemplate.code)
    if family_id:
        query = query.filter(models.AircraftTypeTemplate.family_id == family_id)
    return query.all()


@router.post("/types", response_model=schemas.TemplateRead, status_code=201)
def create_template(
    payload: schemas.TemplateCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_write_user),
):
    return services.create_template(db, payload, current_user.id)


@router.get("/types/{template_id}/revisions", response_model=list[schemas.RevisionRead])
def list_revisions(
    template_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    return (
        db.query(models.AircraftTypeTemplateRevision)
        .options(
            selectinload(models.AircraftTypeTemplateRevision.positions),
            selectinload(models.AircraftTypeTemplateRevision.component_definitions),
            selectinload(models.AircraftTypeTemplateRevision.sources),
        )
        .filter(models.AircraftTypeTemplateRevision.template_id == template_id)
        .order_by(models.AircraftTypeTemplateRevision.created_at.desc())
        .all()
    )


@router.post("/types/{template_id}/revisions", response_model=schemas.RevisionRead, status_code=201)
def create_revision(
    template_id: str,
    payload: schemas.RevisionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_write_user),
):
    return services.create_revision(db, template_id, payload, current_user.id)


@router.get("/revisions/{revision_id}", response_model=schemas.RevisionRead)
def get_revision(
    revision_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    row = (
        db.query(models.AircraftTypeTemplateRevision)
        .options(
            selectinload(models.AircraftTypeTemplateRevision.positions),
            selectinload(models.AircraftTypeTemplateRevision.component_definitions),
            selectinload(models.AircraftTypeTemplateRevision.sources),
        )
        .filter(models.AircraftTypeTemplateRevision.id == revision_id)
        .first()
    )
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Aircraft type revision not found")
    return row


@router.post("/revisions/{revision_id}/positions", response_model=schemas.PositionRead, status_code=201)
def add_position(
    revision_id: str,
    payload: schemas.PositionCreate,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(_write_user),
):
    return services.add_position(db, revision_id, payload)


@router.post(
    "/revisions/{revision_id}/component-definitions",
    response_model=schemas.ComponentDefinitionRead,
    status_code=201,
)
def add_component_definition(
    revision_id: str,
    payload: schemas.ComponentDefinitionCreate,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(_write_user),
):
    return services.add_component_definition(db, revision_id, payload)


@router.post("/revisions/{revision_id}/sources", response_model=schemas.SourceRead, status_code=201)
def add_source(
    revision_id: str,
    payload: schemas.SourceCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_write_user),
):
    return services.add_source(db, revision_id, payload, current_user.id)


@router.post("/revisions/{revision_id}/publish", response_model=schemas.RevisionRead)
def publish_revision(
    revision_id: str,
    payload: schemas.PublishRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_write_user),
):
    return services.publish_revision(db, revision_id, current_user.id, payload.expected_content_hash)
