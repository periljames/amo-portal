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
from amodb.apps.audit import services as audit_services

from . import models, schemas


SOURCE_INTAKE_SCAFFOLDS = (
    {
        "code": "CESSNA_208_SOURCE_INTAKE",
        "manufacturer": "Cessna",
        "family": "208",
        "series": None,
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
        "series": None,
        "description": (
            "Family-level source-intake scaffold for the DHC-8. Series-specific "
            "maintenance planning content is controlled in separate source packs."
        ),
    },
    {
        "code": "DHC8_100_MPD_SOURCE_INTAKE",
        "manufacturer": "De Havilland Canada",
        "family": "DHC-8",
        "series": "100",
        "description": "Controlled OEM maintenance-planning source pack for the DHC-8 Series 100.",
    },
    {
        "code": "DHC8_200_MPD_SOURCE_INTAKE",
        "manufacturer": "De Havilland Canada",
        "family": "DHC-8",
        "series": "200",
        "description": "Controlled OEM maintenance-planning source pack for the DHC-8 Series 200.",
    },
    {
        "code": "DHC8_300_MPD_SOURCE_INTAKE",
        "manufacturer": "De Havilland Canada",
        "family": "DHC-8",
        "series": "300",
        "description": "Controlled OEM maintenance-planning source pack for the DHC-8 Series 300.",
    },
    {
        "code": "DHC8_400_MPD_SOURCE_INTAKE",
        "manufacturer": "De Havilland Canada",
        "family": "DHC-8",
        "series": "400",
        "description": "Controlled OEM maintenance-planning source pack for the DHC-8 Series 400.",
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


def require_active_human(user: account_models.User) -> None:
    if not user.is_active or user.is_system_account:
        raise HTTPException(status_code=403, detail="An active human account is required")


def require_source_contributor(user: account_models.User) -> None:
    require_active_human(user)
    if not (user.is_superuser or user.is_amo_admin):
        raise HTTPException(
            status_code=403,
            detail="Platform superuser or AMO administrator authority is required",
        )


def require_platform_human(user: account_models.User) -> None:
    require_active_human(user)
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Platform superuser authority is required")


def _audit(
    db: Session,
    *,
    user: account_models.User,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    critical: bool = False,
) -> None:
    audit_services.log_event(
        db,
        amo_id=user.amo_id,
        actor_user_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
        metadata={"module": "aircraft_oem_source", **(metadata or {})},
        critical=critical,
    )


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
        elif getattr(row, "series", None) != definition["series"]:
            row.series = definition["series"]
            db.add(row)
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
            for row in sorted(payload.components, key=lambda item: item.definition_code)
        ],
        "tasks": [
            row.model_dump(mode="json")
            for row in sorted(payload.tasks, key=lambda item: item.task_code)
        ],
        "resources": [
            row.model_dump(mode="json")
            for row in sorted(
                payload.resources,
                key=lambda item: (item.resource_kind, item.resource_code),
            )
        ],
    }


def revision_hash(
    pack: models.AircraftContentPack,
    payload: schemas.ContentRevisionCreate,
) -> str:
    return _hash(_ordered_revision_payload(pack, payload))


def _registry_source_check(
    db: Session,
    row: schemas.ContentSourceCreate,
) -> None:
    if not row.publication_revision_id and row.temporary_revision_id:
        raise HTTPException(
            status_code=422,
            detail=f"Source {row.reference} links a temporary revision without its base publication revision",
        )
    if not row.publication_revision_id:
        return
    publication_revision = db.get(
        models.AircraftOemPublicationRevision,
        row.publication_revision_id,
    )
    if not publication_revision:
        raise HTTPException(status_code=422, detail=f"Source {row.reference} publication revision is unknown")
    if publication_revision.status not in {"VERIFIED", "CURRENT", "SUPERSEDED"}:
        raise HTTPException(
            status_code=422,
            detail=f"Source {row.reference} is linked to an unverified OEM publication revision",
        )
    if row.temporary_revision_id:
        temporary = db.get(models.AircraftOemTemporaryRevision, row.temporary_revision_id)
        if not temporary or temporary.publication_revision_id != publication_revision.id:
            raise HTTPException(
                status_code=422,
                detail=f"Source {row.reference} temporary revision does not belong to its base publication revision",
            )
        if temporary.status != "ACTIVE" or temporary.verified_at is None:
            raise HTTPException(
                status_code=422,
                detail=f"Source {row.reference} temporary revision is not an active verified source",
            )
        if row.source_revision != temporary.temporary_revision_code:
            raise HTTPException(
                status_code=422,
                detail=f"Source {row.reference} revision does not match the linked temporary revision",
            )
        if row.checksum_sha256 != temporary.checksum_sha256:
            raise HTTPException(
                status_code=422,
                detail=f"Source {row.reference} checksum does not match the linked temporary revision",
            )
    elif row.source_revision != publication_revision.revision_code:
        raise HTTPException(
            status_code=422,
            detail=f"Source {row.reference} revision does not match the linked OEM publication revision",
        )


def validate_source_backing(
    payload: schemas.ContentRevisionCreate,
    *,
    db: Session | None = None,
) -> None:
    references = {row.reference for row in payload.sources}
    if payload.positions or payload.components or payload.tasks or payload.resources:
        if not payload.sources:
            raise HTTPException(status_code=422, detail="Engineering content requires controlled sources")
    if db is not None:
        for row in payload.sources:
            _registry_source_check(db, row)
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
    for row in payload.resources:
        key = (row.source_reference, row.source_revision, row.source_checksum_sha256)
        if key not in source_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Resource {row.resource_kind}:{row.resource_code} has no exact source match",
            )


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
                    publication_revision_id=row.publication_revision_id,
                    temporary_revision_id=row.temporary_revision_id,
                    source_page_ref=row.source_page_ref,
                    document_locator=row.document_locator,
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
                    description=row.description,
                    ata_chapter=row.ata_chapter,
                    programme_section=row.programme_section,
                    task_type=row.task_type,
                    intervals_json=row.intervals_json,
                    raw_interval_text=row.raw_interval_text,
                    effectivity_expression_json=row.effectivity_expression_json,
                    raw_effectivity_text=row.raw_effectivity_text,
                    source_requirements_json=row.source_requirements_json,
                    task_card_number=row.task_card_number,
                    task_card_configuration=row.task_card_configuration,
                    amm_reference=row.amm_reference,
                    zones_json=row.zones_json,
                    panels_json=row.panels_json,
                    general_references_json=row.general_references_json,
                    skill_code=row.skill_code,
                    labour_hours=row.labour_hours,
                    number_of_persons=row.number_of_persons,
                    program_notes_json=row.program_notes_json,
                    packaging_json=row.packaging_json,
                    source_page_ref=row.source_page_ref,
                    source_reference=row.source_reference,
                    source_revision=row.source_revision,
                    source_checksum_sha256=row.source_checksum_sha256,
                    metadata_json=row.metadata_json,
                )
                for row in revision.tasks
            ],
            resources=[
                schemas.ContentResourceCreate(
                    resource_kind=row.resource_kind,
                    resource_code=row.resource_code,
                    title=row.title,
                    payload_json=row.payload_json,
                    source_reference=row.source_reference,
                    source_revision=row.source_revision,
                    source_checksum_sha256=row.source_checksum_sha256,
                    source_page_ref=row.source_page_ref,
                    metadata_json=row.metadata_json,
                )
                for row in revision.resources
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
    require_source_contributor(user)
    validate_source_backing(payload, db=db)
    _advisory_lock(db, f"aircraft-content-pack:revision:{pack.id}:{payload.revision_code}")
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
    for row in sorted(payload.resources, key=lambda item: (item.resource_kind, item.resource_code)):
        db.add(models.AircraftContentPackResource(revision_id=revision.id, **row.model_dump()))
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_CONTENT_PACK_REVISION",
        entity_id=revision.id,
        action="CREATE_DRAFT",
        after={"pack_id": pack.id, "revision_code": revision.revision_code, "content_hash": revision.content_hash},
    )
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
    validate_source_backing(payload, db=db)
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
    if not (locked.tasks or locked.resources or locked.positions or locked.components):
        raise HTTPException(status_code=409, detail="A content pack cannot be published without controlled engineering content")
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
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_CONTENT_PACK_REVISION",
        entity_id=locked.id,
        action="PUBLISH",
        before={"status": "DRAFT"},
        after={"status": "PUBLISHED", "content_hash": actual_content_hash},
        critical=True,
    )
    db.commit()
    db.refresh(locked)
    return locked


def create_oem_publication(
    db: Session,
    *,
    payload: schemas.OemPublicationCreate,
    user: account_models.User,
) -> models.AircraftOemPublication:
    require_platform_human(user)
    _advisory_lock(db, f"aircraft-oem-publication:{payload.code}")
    if db.query(models.AircraftOemPublication.id).filter(
        models.AircraftOemPublication.code == payload.code
    ).first():
        raise HTTPException(status_code=409, detail="OEM publication already exists")
    row = models.AircraftOemPublication(
        **payload.model_dump(),
        status="ACTIVE",
        created_by_user_id=user.id,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_PUBLICATION",
        entity_id=row.id,
        action="CREATE",
        after=payload.model_dump(mode="json"),
        critical=True,
    )
    db.commit()
    db.refresh(row)
    return row


def submit_oem_publication_revision(
    db: Session,
    *,
    publication: models.AircraftOemPublication,
    payload: schemas.OemPublicationRevisionCreate,
    user: account_models.User,
) -> models.AircraftOemPublicationRevision:
    require_source_contributor(user)
    _advisory_lock(db, f"aircraft-oem-publication-revision:{publication.id}:{payload.revision_code}")
    if db.query(models.AircraftOemPublicationRevision.id).filter(
        models.AircraftOemPublicationRevision.publication_id == publication.id,
        models.AircraftOemPublicationRevision.revision_code == payload.revision_code,
    ).first():
        raise HTTPException(status_code=409, detail="OEM publication revision already exists")
    if payload.supersedes_revision_id:
        supersedes = db.get(models.AircraftOemPublicationRevision, payload.supersedes_revision_id)
        if not supersedes or supersedes.publication_id != publication.id:
            raise HTTPException(status_code=422, detail="Superseded revision must belong to the same publication")
    row = models.AircraftOemPublicationRevision(
        publication_id=publication.id,
        **payload.model_dump(),
        status="CANDIDATE",
        submitted_by_user_id=user.id,
        submitted_by_amo_id=user.amo_id,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_PUBLICATION_REVISION",
        entity_id=row.id,
        action="SUBMIT_CANDIDATE",
        after={
            "publication_id": publication.id,
            "revision_code": row.revision_code,
            "checksum_sha256": row.checksum_sha256,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def decide_oem_publication_revision(
    db: Session,
    *,
    revision: models.AircraftOemPublicationRevision,
    payload: schemas.OemPublicationRevisionDecision,
    user: account_models.User,
) -> models.AircraftOemPublicationRevision:
    require_platform_human(user)
    _advisory_lock(db, f"aircraft-oem-publication-decision:{revision.publication_id}")
    locked = (
        db.query(models.AircraftOemPublicationRevision)
        .filter(models.AircraftOemPublicationRevision.id == revision.id)
        .with_for_update(of=models.AircraftOemPublicationRevision)
        .one()
    )
    before = locked.status
    now = datetime.now(timezone.utc)
    if payload.action == "VERIFY":
        if locked.status != "CANDIDATE":
            raise HTTPException(status_code=409, detail="Only candidate OEM revisions can be verified")
        locked.status = "VERIFIED"
        locked.verified_by_user_id = user.id
        locked.verified_at = now
    elif payload.action == "MAKE_CURRENT":
        if locked.status not in {"VERIFIED", "CURRENT"}:
            raise HTTPException(status_code=409, detail="Only verified OEM revisions can become current")
        current_rows = (
            db.query(models.AircraftOemPublicationRevision)
            .filter(
                models.AircraftOemPublicationRevision.publication_id == locked.publication_id,
                models.AircraftOemPublicationRevision.status == "CURRENT",
                models.AircraftOemPublicationRevision.id != locked.id,
            )
            .with_for_update(of=models.AircraftOemPublicationRevision)
            .all()
        )
        for current in current_rows:
            current.status = "SUPERSEDED"
            db.add(current)
        locked.status = "CURRENT"
        if locked.verified_at is None:
            locked.verified_at = now
            locked.verified_by_user_id = user.id
    elif payload.action == "REJECT":
        if locked.status not in {"CANDIDATE", "VERIFIED"}:
            raise HTTPException(status_code=409, detail="Only candidate or verified OEM revisions can be rejected")
        locked.status = "REJECTED"
    elif payload.action == "WITHDRAW":
        if locked.status == "CURRENT":
            raise HTTPException(status_code=409, detail="A current OEM revision must be superseded before withdrawal")
        if locked.status in {"WITHDRAWN", "REJECTED"}:
            raise HTTPException(status_code=409, detail="OEM revision is already closed")
        locked.status = "WITHDRAWN"
    metadata = dict(locked.metadata_json or {})
    metadata.setdefault("decisions", []).append(
        {
            "action": payload.action,
            "note": payload.decision_note,
            "actor_user_id": user.id,
            "at": now.isoformat(),
        }
    )
    locked.metadata_json = metadata
    db.add(locked)
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_PUBLICATION_REVISION",
        entity_id=locked.id,
        action=payload.action,
        before={"status": before},
        after={"status": locked.status},
        metadata={"decision_note": payload.decision_note},
        critical=True,
    )
    db.commit()
    db.refresh(locked)
    return locked


def create_temporary_revision(
    db: Session,
    *,
    publication_revision: models.AircraftOemPublicationRevision,
    payload: schemas.OemTemporaryRevisionCreate,
    user: account_models.User,
) -> models.AircraftOemTemporaryRevision:
    require_source_contributor(user)
    if publication_revision.status not in {"VERIFIED", "CURRENT", "SUPERSEDED"}:
        raise HTTPException(status_code=409, detail="Temporary revisions require a verified base publication revision")
    _advisory_lock(
        db,
        f"aircraft-oem-tr:{publication_revision.id}:{payload.temporary_revision_code}",
    )
    if db.query(models.AircraftOemTemporaryRevision.id).filter(
        models.AircraftOemTemporaryRevision.publication_revision_id == publication_revision.id,
        models.AircraftOemTemporaryRevision.temporary_revision_code == payload.temporary_revision_code,
    ).first():
        raise HTTPException(status_code=409, detail="Temporary revision already exists")
    now = datetime.now(timezone.utc)
    row = models.AircraftOemTemporaryRevision(
        publication_revision_id=publication_revision.id,
        **payload.model_dump(),
        status="ACTIVE",
        submitted_by_user_id=user.id,
        submitted_by_amo_id=user.amo_id,
        verified_by_user_id=user.id if user.is_superuser else None,
        verified_at=now if user.is_superuser else None,
    )
    db.add(row)
    db.flush()
    if payload.replaces_temporary_revision_code:
        prior = db.query(models.AircraftOemTemporaryRevision).filter(
            models.AircraftOemTemporaryRevision.publication_revision_id == publication_revision.id,
            models.AircraftOemTemporaryRevision.temporary_revision_code == payload.replaces_temporary_revision_code,
            models.AircraftOemTemporaryRevision.status == "ACTIVE",
        ).first()
        if prior:
            prior.status = "REPLACED"
            db.add(prior)
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_TEMPORARY_REVISION",
        entity_id=row.id,
        action="SUBMIT",
        after={
            "temporary_revision_code": row.temporary_revision_code,
            "status": row.status,
            "verified": row.verified_at is not None,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def decide_temporary_revision(
    db: Session,
    *,
    temporary_revision: models.AircraftOemTemporaryRevision,
    payload: schemas.OemTemporaryRevisionDecision,
    user: account_models.User,
) -> models.AircraftOemTemporaryRevision:
    require_platform_human(user)
    _advisory_lock(db, f"aircraft-oem-tr-decision:{temporary_revision.id}")
    row = (
        db.query(models.AircraftOemTemporaryRevision)
        .filter(models.AircraftOemTemporaryRevision.id == temporary_revision.id)
        .with_for_update(of=models.AircraftOemTemporaryRevision)
        .one()
    )
    before = row.status
    if payload.status == "ACTIVE":
        row.status = "ACTIVE"
        row.verified_by_user_id = user.id
        row.verified_at = datetime.now(timezone.utc)
    else:
        row.status = payload.status
    metadata = dict(row.metadata_json or {})
    metadata.setdefault("decisions", []).append(
        {
            "status": payload.status,
            "note": payload.decision_note,
            "actor_user_id": user.id,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    row.metadata_json = metadata
    db.add(row)
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_TEMPORARY_REVISION",
        entity_id=row.id,
        action="SET_STATUS",
        before={"status": before},
        after={"status": row.status, "verified": row.verified_at is not None},
        metadata={"decision_note": payload.decision_note},
        critical=True,
    )
    db.commit()
    db.refresh(row)
    return row


def create_source_watch(
    db: Session,
    *,
    publication: models.AircraftOemPublication,
    payload: schemas.OemSourceWatchCreate,
    user: account_models.User,
) -> models.AircraftOemSourceWatch:
    require_source_contributor(user)
    row = models.AircraftOemSourceWatch(
        publication_id=publication.id,
        **payload.model_dump(),
        created_by_user_id=user.id,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Source watch already exists") from exc
    db.refresh(row)
    return row


def record_source_watch_check(
    db: Session,
    *,
    watch: models.AircraftOemSourceWatch,
    payload: schemas.OemSourceWatchCheck,
    user: account_models.User,
) -> models.AircraftOemSourceWatch:
    require_source_contributor(user)
    watch.last_checked_at = datetime.now(timezone.utc)
    watch.last_seen_marker = payload.seen_marker
    watch.last_result = payload.result
    db.add(watch)
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_SOURCE_WATCH",
        entity_id=watch.id,
        action="CHECK",
        after={"seen_marker": payload.seen_marker, "result": payload.result},
    )
    db.commit()
    db.refresh(watch)
    return watch


def publication_currentness(
    db: Session,
    *,
    publication: models.AircraftOemPublication,
) -> schemas.OemPublicationCurrentnessRead:
    revisions = db.query(models.AircraftOemPublicationRevision).filter(
        models.AircraftOemPublicationRevision.publication_id == publication.id
    ).order_by(models.AircraftOemPublicationRevision.created_at.desc()).all()
    current = next((row for row in revisions if row.status == "CURRENT"), None)
    candidate = next((row for row in revisions if row.status in {"CANDIDATE", "VERIFIED"}), None)
    active_trs: list[models.AircraftOemTemporaryRevision] = []
    if current:
        active_trs = db.query(models.AircraftOemTemporaryRevision).filter(
            models.AircraftOemTemporaryRevision.publication_revision_id == current.id,
            models.AircraftOemTemporaryRevision.status == "ACTIVE",
        ).order_by(models.AircraftOemTemporaryRevision.issue_date, models.AircraftOemTemporaryRevision.created_at).all()
    watches = db.query(models.AircraftOemSourceWatch).filter(
        models.AircraftOemSourceWatch.publication_id == publication.id,
        models.AircraftOemSourceWatch.is_active.is_(True),
    ).order_by(models.AircraftOemSourceWatch.channel_type, models.AircraftOemSourceWatch.reference).all()
    if current is None:
        status = "NO_CURRENT_REVISION"
    elif any(row.verified_at is None for row in active_trs):
        status = "SOURCE_CHECK_REQUIRED"
    elif candidate is not None:
        status = "CANDIDATE_REVIEW_REQUIRED"
    elif active_trs:
        status = "TEMPORARY_REVISION_ACTIVE"
    elif any(row.last_checked_at is None for row in watches):
        status = "SOURCE_CHECK_REQUIRED"
    else:
        status = "CURRENT"
    return schemas.OemPublicationCurrentnessRead(
        publication=schemas.OemPublicationRead.model_validate(publication),
        current_revision=(
            schemas.OemPublicationRevisionRead.model_validate(current) if current else None
        ),
        newest_candidate=(
            schemas.OemPublicationRevisionRead.model_validate(candidate) if candidate else None
        ),
        active_temporary_revisions=[
            schemas.OemTemporaryRevisionRead.model_validate(row) for row in active_trs
        ],
        watches=[schemas.OemSourceWatchRead.model_validate(row) for row in watches],
        currentness_status=status,
    )


def _controlled_task_payload(row: models.AircraftContentPackTask) -> dict[str, Any]:
    return {
        "title": row.title,
        "description": row.description,
        "ata_chapter": row.ata_chapter,
        "programme_section": row.programme_section,
        "task_type": row.task_type,
        "intervals_json": row.intervals_json,
        "raw_interval_text": row.raw_interval_text,
        "effectivity_expression_json": row.effectivity_expression_json,
        "raw_effectivity_text": row.raw_effectivity_text,
        "source_requirements_json": row.source_requirements_json,
        "task_card_number": row.task_card_number,
        "task_card_configuration": row.task_card_configuration,
        "amm_reference": row.amm_reference,
        "zones_json": row.zones_json,
        "panels_json": row.panels_json,
        "general_references_json": row.general_references_json,
        "skill_code": row.skill_code,
        "labour_hours": row.labour_hours,
        "number_of_persons": row.number_of_persons,
        "program_notes_json": row.program_notes_json,
        "packaging_json": row.packaging_json,
        "source_page_ref": row.source_page_ref,
        "source_reference": row.source_reference,
        "source_revision": row.source_revision,
        "source_checksum_sha256": row.source_checksum_sha256,
        "metadata_json": row.metadata_json,
    }


def _controlled_resource_payload(row: models.AircraftContentPackResource) -> dict[str, Any]:
    return {
        "title": row.title,
        "payload_json": row.payload_json,
        "source_reference": row.source_reference,
        "source_revision": row.source_revision,
        "source_checksum_sha256": row.source_checksum_sha256,
        "source_page_ref": row.source_page_ref,
        "metadata_json": row.metadata_json,
    }


def compare_content_revisions(
    base: models.AircraftContentPackRevision,
    target: models.AircraftContentPackRevision,
) -> schemas.ContentRevisionDiffRead:
    if base.pack_id != target.pack_id:
        raise HTTPException(status_code=422, detail="Content revisions must belong to the same pack")
    base_tasks = {row.task_code: _hash(_controlled_task_payload(row)) for row in base.tasks}
    target_tasks = {row.task_code: _hash(_controlled_task_payload(row)) for row in target.tasks}
    base_resources = {
        f"{row.resource_kind}:{row.resource_code}": _hash(_controlled_resource_payload(row))
        for row in base.resources
    }
    target_resources = {
        f"{row.resource_kind}:{row.resource_code}": _hash(_controlled_resource_payload(row))
        for row in target.resources
    }
    common_tasks = set(base_tasks) & set(target_tasks)
    return schemas.ContentRevisionDiffRead(
        base_revision_id=base.id,
        target_revision_id=target.id,
        added_tasks=sorted(set(target_tasks) - set(base_tasks)),
        removed_tasks=sorted(set(base_tasks) - set(target_tasks)),
        changed_tasks=sorted(code for code in common_tasks if base_tasks[code] != target_tasks[code]),
        unchanged_tasks=sum(base_tasks[code] == target_tasks[code] for code in common_tasks),
        added_resources=sorted(set(target_resources) - set(base_resources)),
        removed_resources=sorted(set(base_resources) - set(target_resources)),
        changed_resources=sorted(
            code
            for code in set(base_resources) & set(target_resources)
            if base_resources[code] != target_resources[code]
        ),
    )
