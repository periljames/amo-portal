from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import models, schemas


SOURCE_INTAKE_SCAFFOLDS = (
    {
        "code": "CESSNA_208_SOURCE_INTAKE",
        "manufacturer": "Cessna",
        "family": "208",
        "description": (
            "Source-intake scaffold for the Cessna 208 family. It contains no "
            "maintenance tasks, intervals, positions or components until approved "
            "OEM/operator source material is supplied."
        ),
    },
    {
        "code": "DHC8_SOURCE_INTAKE",
        "manufacturer": "De Havilland Canada",
        "family": "DHC-8",
        "description": (
            "Source-intake scaffold for the DHC-8 family. It contains no "
            "maintenance tasks, intervals, positions or components until approved "
            "OEM/operator source material is supplied."
        ),
    },
)


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _advisory_lock(db: Session, key: str) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": key},
    )


def require_platform_human(user: account_models.User) -> None:
    if not user.is_active or user.is_system_account:
        raise HTTPException(status_code=403, detail="An active human platform account is required")
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Platform superuser authority is required")


def bootstrap_source_intake_packs(
    db: Session,
    *,
    user: account_models.User,
) -> list[models.AircraftContentPack]:
    require_platform_human(user)
    _advisory_lock(db, "aircraft-content-pack:source-intake-bootstrap")
    rows: list[models.AircraftContentPack] = []
    for definition in SOURCE_INTAKE_SCAFFOLDS:
        row = db.query(models.AircraftContentPack).filter(
            models.AircraftContentPack.code == definition["code"]
        ).first()
        if not row:
            row = models.AircraftContentPack(
                **definition,
                status="SOURCE_INTAKE",
                created_by_user_id=user.id,
            )
            db.add(row)
            db.flush()
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def _ordered_revision_payload(
    pack: models.AircraftContentPack,
    payload: schemas.ContentRevisionCreate,
) -> dict[str, Any]:
    return {
        "pack_code": pack.code,
        "revision_code": payload.revision_code,
        "sources": [
            row.model_dump(mode="json")
            for row in sorted(
                payload.sources,
                key=lambda item: (
                    item.reference,
                    item.source_revision,
                    item.checksum_sha256,
                ),
            )
        ],
        "positions": [
            row.model_dump(mode="json")
            for row in sorted(payload.positions, key=lambda item: item.code)
        ],
        "components": [
            row.model_dump(mode="json")
            for row in sorted(
                payload.components,
                key=lambda item: item.definition_code,
            )
        ],
        "tasks": [
            row.model_dump(mode="json")
            for row in sorted(payload.tasks, key=lambda item: item.task_code)
        ],
    }


def revision_hash(
    pack: models.AircraftContentPack,
    payload: schemas.ContentRevisionCreate,
) -> str:
    return _hash(_ordered_revision_payload(pack, payload))


def validate_source_backing(payload: schemas.ContentRevisionCreate) -> None:
    references = {row.reference for row in payload.sources}
    if payload.positions or payload.components or payload.tasks:
        if not payload.sources:
            raise HTTPException(status_code=422, detail="Engineering content requires controlled sources")
    for row in payload.positions:
        if row.source_reference not in references:
            raise HTTPException(status_code=422, detail=f"Position {row.code} has no matching source")
    position_codes = {row.code for row in payload.positions}
    for row in payload.components:
        if row.position_code not in position_codes:
            raise HTTPException(
                status_code=422,
                detail=f"Component {row.definition_code} references an unknown position",
            )
        if row.source_reference not in references:
            raise HTTPException(status_code=422, detail=f"Component {row.definition_code} has no matching source")
    source_keys = {(row.reference, row.source_revision, row.checksum_sha256) for row in payload.sources}
    for row in payload.tasks:
        key = (row.source_reference, row.source_revision, row.source_checksum_sha256)
        if key not in source_keys:
            raise HTTPException(status_code=422, detail=f"Task {row.task_code} has no exact source match")


def _payload_from_revision(
    revision: models.AircraftContentPackRevision,
) -> schemas.ContentRevisionCreate:
    try:
        return schemas.ContentRevisionCreate(
            revision_code=revision.revision_code,
            change_summary=revision.change_summary,
            sources=[
                schemas.ContentSourceCreate(
                    source_type=row.source_type,
                    reference=row.reference,
                    source_revision=row.source_revision,
                    effective_date=row.effective_date,
                    checksum_sha256=row.checksum_sha256,
                    authority=row.authority,
                    provenance_json=row.provenance_json,
                )
                for row in revision.sources
            ],
            positions=[
                schemas.ContentPositionCreate(
                    code=row.code,
                    label=row.label,
                    position_kind=row.position_kind,
                    required=row.required,
                    source_reference=row.source_reference,
                    metadata_json=row.metadata_json,
                )
                for row in revision.positions
            ],
            components=[
                schemas.ContentComponentCreate(
                    definition_code=row.definition_code,
                    position_code=row.position_code,
                    description=row.description,
                    component_class=row.component_class,
                    accepted_part_numbers_json=row.accepted_part_numbers_json,
                    life_limit_json=row.life_limit_json,
                    metadata_json=row.metadata_json,
                    source_reference=row.source_reference,
                )
                for row in revision.components
            ],
            tasks=[
                schemas.ContentTaskCreate(
                    task_code=row.task_code,
                    title=row.title,
                    ata_chapter=row.ata_chapter,
                    intervals_json=row.intervals_json,
                    effectivity_expression_json=row.effectivity_expression_json,
                    source_reference=row.source_reference,
                    source_revision=row.source_revision,
                    source_checksum_sha256=row.source_checksum_sha256,
                    metadata_json=row.metadata_json,
                )
                for row in revision.tasks
            ],
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail="Content-pack revision contains invalid or incomplete controlled content",
        ) from exc


def create_revision(
    db: Session,
    *,
    pack: models.AircraftContentPack,
    payload: schemas.ContentRevisionCreate,
    user: account_models.User,
) -> models.AircraftContentPackRevision:
    require_platform_human(user)
    validate_source_backing(payload)
    _advisory_lock(
        db,
        f"aircraft-content-pack:revision:{pack.id}:{payload.revision_code}",
    )
    duplicate = db.query(models.AircraftContentPackRevision.id).filter(
        models.AircraftContentPackRevision.pack_id == pack.id,
        models.AircraftContentPackRevision.revision_code == payload.revision_code,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Content-pack revision already exists")
    revision = models.AircraftContentPackRevision(
        pack_id=pack.id,
        revision_code=payload.revision_code,
        change_summary=payload.change_summary,
        content_hash=revision_hash(pack, payload),
        created_by_user_id=user.id,
    )
    db.add(revision)
    db.flush()
    for row in sorted(
        payload.sources,
        key=lambda item: (item.reference, item.source_revision, item.checksum_sha256),
    ):
        db.add(models.AircraftContentPackSource(revision_id=revision.id, **row.model_dump()))
    for row in sorted(payload.positions, key=lambda item: item.code):
        db.add(models.AircraftContentPackPosition(revision_id=revision.id, **row.model_dump()))
    for row in sorted(payload.components, key=lambda item: item.definition_code):
        db.add(models.AircraftContentPackComponent(revision_id=revision.id, **row.model_dump()))
    for row in sorted(payload.tasks, key=lambda item: item.task_code):
        db.add(models.AircraftContentPackTask(revision_id=revision.id, **row.model_dump()))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Content-pack revision conflicts with existing data") from exc
    db.refresh(revision)
    return revision


def publish_revision(
    db: Session,
    *,
    revision: models.AircraftContentPackRevision,
    expected_content_hash: str,
    user: account_models.User,
) -> models.AircraftContentPackRevision:
    require_platform_human(user)
    _advisory_lock(db, f"aircraft-content-pack:publish:{revision.id}")
    locked = (
        db.query(models.AircraftContentPackRevision)
        .filter(models.AircraftContentPackRevision.id == revision.id)
        .populate_existing()
        .with_for_update(of=models.AircraftContentPackRevision)
        .one()
    )
    payload = _payload_from_revision(locked)
    validate_source_backing(payload)
    actual_content_hash = revision_hash(locked.pack, payload)
    if locked.content_hash != actual_content_hash:
        raise HTTPException(status_code=409, detail="Content-pack content changed after hashing")
    if expected_content_hash != actual_content_hash:
        raise HTTPException(status_code=409, detail="Content-pack content changed after review")
    if locked.status == "PUBLISHED":
        return locked
    if locked.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft content-pack revisions can be published")
    if not locked.sources:
        raise HTTPException(status_code=409, detail="A content pack cannot be published without controlled sources")
    if not locked.positions:
        raise HTTPException(status_code=409, detail="A content pack cannot be published without source-backed positions")
    previous = (
        db.query(models.AircraftContentPackRevision)
        .filter(
            models.AircraftContentPackRevision.pack_id == locked.pack_id,
            models.AircraftContentPackRevision.status == "PUBLISHED",
            models.AircraftContentPackRevision.id != locked.id,
        )
        .with_for_update(of=models.AircraftContentPackRevision)
        .all()
    )
    for row in previous:
        row.status = "SUPERSEDED"
        db.add(row)
    locked.status = "PUBLISHED"
    locked.published_by_user_id = user.id
    locked.published_at = datetime.now(timezone.utc)
    locked.pack.status = "ACTIVE"
    db.add(locked)
    db.add(locked.pack)
    db.commit()
    db.refresh(locked)
    return locked
