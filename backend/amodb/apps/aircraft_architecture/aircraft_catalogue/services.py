from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from . import models, schemas


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_revision_hash(revision: models.AircraftTypeTemplateRevision) -> str:
    payload = {
        "template_code": revision.template.code,
        "manufacturer": revision.template.manufacturer,
        "model": revision.template.model,
        "variant": revision.template.variant,
        "series": revision.template.series,
        "revision_code": revision.revision_code,
        "effective_date": revision.effective_date,
        "configuration_schema": revision.configuration_schema_json or {},
        "applicability_defaults": revision.applicability_defaults_json or {},
        "positions": sorted(
            [
                {
                    "code": item.code,
                    "label": item.label,
                    "kind": item.position_kind,
                    "parent": item.parent_code,
                    "sequence": item.sequence_no,
                    "required": item.required,
                    "metadata": item.metadata_json or {},
                    "effectivity": item.effectivity_json or {},
                }
                for item in revision.positions
            ],
            key=lambda row: row["code"],
        ),
        "component_definitions": sorted(
            [
                {
                    "code": item.definition_code,
                    "position": item.position_code,
                    "description": item.description,
                    "class": item.component_class,
                    "part_numbers": item.accepted_part_numbers_json or [],
                    "life_limit": item.life_limit_json or {},
                    "effectivity": item.effectivity_json or {},
                    "metadata": item.metadata_json or {},
                }
                for item in revision.component_definitions
            ],
            key=lambda row: row["code"],
        ),
        "sources": sorted(
            [
                {
                    "type": item.source_type,
                    "reference": item.reference,
                    "revision": item.source_revision,
                    "effective_date": item.effective_date,
                    "checksum": item.checksum_sha256,
                    "authority": item.authority,
                    "provenance": item.provenance_json or {},
                }
                for item in revision.sources
            ],
            key=lambda row: (row["type"], row["reference"], row["revision"]),
        ),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def require_catalogue_writer(user: Any) -> None:
    if not bool(getattr(user, "is_superuser", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform superusers may change the global aircraft type catalogue.",
        )


def _revision(db: Session, revision_id: str) -> models.AircraftTypeTemplateRevision:
    row = db.get(models.AircraftTypeTemplateRevision, revision_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aircraft type revision not found")
    return row


def require_draft(revision: models.AircraftTypeTemplateRevision) -> None:
    if revision.status != "DRAFT":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Published, superseded and withdrawn aircraft type revisions are immutable.",
        )


def create_family(db: Session, payload: schemas.FamilyCreate, actor_id: str | None) -> models.AircraftFamily:
    if db.query(models.AircraftFamily.id).filter(models.AircraftFamily.code == payload.code).first():
        raise HTTPException(status_code=409, detail="Aircraft family code already exists")
    row = models.AircraftFamily(**payload.model_dump(), created_by_user_id=actor_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_template(db: Session, payload: schemas.TemplateCreate, actor_id: str | None) -> models.AircraftTypeTemplate:
    if not db.get(models.AircraftFamily, payload.family_id):
        raise HTTPException(status_code=404, detail="Aircraft family not found")
    if db.query(models.AircraftTypeTemplate.id).filter(models.AircraftTypeTemplate.code == payload.code).first():
        raise HTTPException(status_code=409, detail="Aircraft type template code already exists")
    row = models.AircraftTypeTemplate(**payload.model_dump(), created_by_user_id=actor_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_revision(
    db: Session,
    template_id: str,
    payload: schemas.RevisionCreate,
    actor_id: str | None,
) -> models.AircraftTypeTemplateRevision:
    template = db.get(models.AircraftTypeTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Aircraft type template not found")
    if payload.supersedes_revision_id:
        previous = _revision(db, payload.supersedes_revision_id)
        if previous.template_id != template_id or previous.status not in {"PUBLISHED", "SUPERSEDED"}:
            raise HTTPException(status_code=409, detail="Superseded revision must be a published revision of the same type")
    duplicate = (
        db.query(models.AircraftTypeTemplateRevision.id)
        .filter(
            models.AircraftTypeTemplateRevision.template_id == template_id,
            models.AircraftTypeTemplateRevision.revision_code == payload.revision_code,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Revision code already exists for this aircraft type")
    row = models.AircraftTypeTemplateRevision(
        template_id=template_id,
        **payload.model_dump(),
        created_by_user_id=actor_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_position(
    db: Session,
    revision_id: str,
    payload: schemas.PositionCreate,
) -> models.AircraftTypePosition:
    revision = _revision(db, revision_id)
    require_draft(revision)
    if payload.parent_code and not (
        db.query(models.AircraftTypePosition.id)
        .filter(
            models.AircraftTypePosition.revision_id == revision_id,
            models.AircraftTypePosition.code == payload.parent_code,
        )
        .first()
    ):
        raise HTTPException(status_code=409, detail="Parent position must exist in the same revision")
    row = models.AircraftTypePosition(
        revision_id=revision_id,
        **payload.model_dump(exclude={"required"}),
        required=payload.required,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_component_definition(
    db: Session,
    revision_id: str,
    payload: schemas.ComponentDefinitionCreate,
) -> models.AircraftTypeComponentDefinition:
    revision = _revision(db, revision_id)
    require_draft(revision)
    position = (
        db.query(models.AircraftTypePosition.id)
        .filter(
            models.AircraftTypePosition.revision_id == revision_id,
            models.AircraftTypePosition.code == payload.position_code.upper(),
        )
        .first()
    )
    if not position:
        raise HTTPException(status_code=409, detail="Component definition position is not defined in this revision")
    values = payload.model_dump()
    values["definition_code"] = payload.definition_code.strip().upper()
    values["position_code"] = payload.position_code.strip().upper()
    row = models.AircraftTypeComponentDefinition(revision_id=revision_id, **values)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_source(
    db: Session,
    revision_id: str,
    payload: schemas.SourceCreate,
    actor_id: str | None,
) -> models.AircraftTypeSource:
    revision = _revision(db, revision_id)
    require_draft(revision)
    values = payload.model_dump()
    values["checksum_sha256"] = (
        payload.checksum_sha256.lower() if payload.checksum_sha256 else None
    )
    row = models.AircraftTypeSource(
        revision_id=revision_id,
        **values,
        created_by_user_id=actor_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def publish_revision(
    db: Session,
    revision_id: str,
    actor_id: str | None,
    expected_hash: str | None,
) -> models.AircraftTypeTemplateRevision:
    revision = _revision(db, revision_id)
    require_draft(revision)
    # The draft may have been held in the identity map while positions/sources
    # were added by separate controlled writes. Re-read its children before the
    # publication gate so provenance/configuration checks are based on database
    # truth rather than a stale relationship cache.
    db.flush()
    db.expire(revision, ["positions", "component_definitions", "sources"])
    if not revision.sources:
        raise HTTPException(status_code=409, detail="A revision cannot be published without source provenance")
    if not revision.positions:
        raise HTTPException(status_code=409, detail="A revision cannot be published without a configuration position model")
    actual_hash = compute_revision_hash(revision)
    if expected_hash and expected_hash != actual_hash:
        raise HTTPException(status_code=409, detail="Revision content changed after review; refresh before publishing")

    currently_published = (
        db.query(models.AircraftTypeTemplateRevision)
        .filter(
            models.AircraftTypeTemplateRevision.template_id == revision.template_id,
            models.AircraftTypeTemplateRevision.status == "PUBLISHED",
        )
        # AircraftTypeTemplateRevision has eager joined relationships. PostgreSQL
        # rejects an unqualified FOR UPDATE when that query contains nullable
        # outer-join targets. Lock only the revision rows that control the
        # publication transition.
        .with_for_update(of=models.AircraftTypeTemplateRevision)
        .all()
    )
    for previous in currently_published:
        previous.status = "SUPERSEDED"
        db.add(previous)

    revision.content_hash = actual_hash
    revision.status = "PUBLISHED"
    revision.published_by_user_id = actor_id
    revision.published_at = datetime.now(timezone.utc)
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision
