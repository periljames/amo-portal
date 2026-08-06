from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
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
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def revision_hash(
    pack: models.AircraftContentPack,
    payload: schemas.ContentRevisionCreate,
) -> str:
    return _hash(
        {
            "pack_code": pack.code,
            "revision_code": payload.revision_code,
            "sources": [row.model_dump(mode="json") for row in payload.sources],
            "positions": [row.model_dump(mode="json") for row in payload.positions],
            "components": [row.model_dump(mode="json") for row in payload.components],
            "tasks": [row.model_dump(mode="json") for row in payload.tasks],
        }
    )


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


def create_revision(
    db: Session,
    *,
    pack: models.AircraftContentPack,
    payload: schemas.ContentRevisionCreate,
    user: account_models.User,
) -> models.AircraftContentPackRevision:
    require_platform_human(user)
    validate_source_backing(payload)
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
    for row in payload.sources:
        db.add(models.AircraftContentPackSource(revision_id=revision.id, **row.model_dump()))
    for row in payload.positions:
        db.add(models.AircraftContentPackPosition(revision_id=revision.id, **row.model_dump()))
    for row in payload.components:
        db.add(models.AircraftContentPackComponent(revision_id=revision.id, **row.model_dump()))
    for row in payload.tasks:
        db.add(models.AircraftContentPackTask(revision_id=revision.id, **row.model_dump()))
    db.commit()
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
    if revision.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft content-pack revisions can be published")
    if revision.content_hash != expected_content_hash:
        raise HTTPException(status_code=409, detail="Content-pack content changed after review")
    if not revision.sources:
        raise HTTPException(status_code=409, detail="A content pack cannot be published without controlled sources")
    if not revision.positions:
        raise HTTPException(status_code=409, detail="A content pack cannot be published without source-backed positions")
    previous = db.query(models.AircraftContentPackRevision).filter(
        models.AircraftContentPackRevision.pack_id == revision.pack_id,
        models.AircraftContentPackRevision.status == "PUBLISHED",
    ).with_for_update(of=models.AircraftContentPackRevision).all()
    for row in previous:
        row.status = "SUPERSEDED"
        db.add(row)
    revision.status = "PUBLISHED"
    revision.published_by_user_id = user.id
    revision.published_at = datetime.now(timezone.utc)
    revision.pack.status = "ACTIVE"
    db.add(revision)
    db.add(revision.pack)
    db.commit()
    db.refresh(revision)
    return revision
