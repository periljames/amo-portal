from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, noload

from . import backend_schemas, models, schemas


ENTITY_MODELS = {
    "tasks": (
        models.AircraftContentPackTask,
        models.AircraftContentPackTask.task_code,
        schemas.ContentTaskRead,
    ),
    "resources": (
        models.AircraftContentPackResource,
        models.AircraftContentPackResource.resource_kind,
        schemas.ContentResourceRead,
    ),
    "positions": (
        models.AircraftContentPackPosition,
        models.AircraftContentPackPosition.code,
        backend_schemas.ContentPositionFullRead,
    ),
    "components": (
        models.AircraftContentPackComponent,
        models.AircraftContentPackComponent.definition_code,
        backend_schemas.ContentComponentFullRead,
    ),
}


def revision_without_collections(
    db: Session,
    revision_id: str,
) -> models.AircraftContentPackRevision | None:
    return (
        db.query(models.AircraftContentPackRevision)
        .options(
            noload(models.AircraftContentPackRevision.sources),
            noload(models.AircraftContentPackRevision.positions),
            noload(models.AircraftContentPackRevision.components),
            noload(models.AircraftContentPackRevision.tasks),
            noload(models.AircraftContentPackRevision.resources),
        )
        .filter(models.AircraftContentPackRevision.id == revision_id)
        .first()
    )


def revision_overview(
    db: Session,
    revision_id: str,
) -> dict[str, Any] | None:
    revision = revision_without_collections(db, revision_id)
    if revision is None:
        return None
    counts = {
        "sources": db.query(func.count(models.AircraftContentPackSource.id))
        .filter(models.AircraftContentPackSource.revision_id == revision.id)
        .scalar(),
        "positions": db.query(func.count(models.AircraftContentPackPosition.id))
        .filter(models.AircraftContentPackPosition.revision_id == revision.id)
        .scalar(),
        "components": db.query(func.count(models.AircraftContentPackComponent.id))
        .filter(models.AircraftContentPackComponent.revision_id == revision.id)
        .scalar(),
        "tasks": db.query(func.count(models.AircraftContentPackTask.id))
        .filter(models.AircraftContentPackTask.revision_id == revision.id)
        .scalar(),
        "resources": db.query(func.count(models.AircraftContentPackResource.id))
        .filter(models.AircraftContentPackResource.revision_id == revision.id)
        .scalar(),
    }
    return {
        "revision": schemas.ContentRevisionRead.model_validate(revision).model_dump(mode="json"),
        "counts": {key: int(value or 0) for key, value in counts.items()},
    }


def page_revision_entities(
    db: Session,
    *,
    revision_id: str,
    entity: str,
    offset: int,
    limit: int,
) -> tuple[int, list[dict[str, Any]]]:
    try:
        model, primary_order, schema = ENTITY_MODELS[entity]
    except KeyError as exc:
        raise ValueError(f"Unsupported content entity: {entity}") from exc
    query = db.query(model).filter(model.revision_id == revision_id)
    total = int(query.count())
    if entity == "resources":
        rows = (
            query.order_by(
                models.AircraftContentPackResource.resource_kind,
                models.AircraftContentPackResource.resource_code,
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
    else:
        rows = query.order_by(primary_order).offset(offset).limit(limit).all()
    return total, [schema.model_validate(row).model_dump(mode="json") for row in rows]


def page_revision_sources(
    db: Session,
    *,
    revision_id: str,
    offset: int,
    limit: int,
) -> tuple[int, list[dict[str, Any]]]:
    query = db.query(models.AircraftContentPackSource).filter(
        models.AircraftContentPackSource.revision_id == revision_id
    )
    total = int(query.count())
    rows = (
        query.order_by(
            models.AircraftContentPackSource.reference,
            models.AircraftContentPackSource.source_revision,
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, [
        schemas.ContentSourceRead.model_validate(row).model_dump(mode="json")
        for row in rows
    ]
