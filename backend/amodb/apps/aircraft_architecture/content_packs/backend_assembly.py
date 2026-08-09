from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import (
    backend_models,
    backend_services,
    governance,
    models,
    schemas,
    services as legacy_services,
)


class OemBaselineConflictResolution(BaseModel):
    row_kind: Literal["TASK", "RESOURCE"]
    identity_key: str = Field(min_length=1, max_length=180)
    selected_intake_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=4000)


class OemBaselineAssemblyCreate(BaseModel):
    revision_code: str = Field(min_length=1, max_length=40)
    intake_hashes: dict[str, str] = Field(min_length=1)
    conflict_resolutions: list[OemBaselineConflictResolution] = Field(default_factory=list)
    change_summary: str | None = Field(default=None, max_length=8000)

    @field_validator("intake_hashes")
    @classmethod
    def hashes_are_exact_sha256(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for intake_id, checksum in value.items():
            intake_id = intake_id.strip()
            checksum = checksum.strip().lower()
            if not intake_id:
                raise ValueError("intake id cannot be empty")
            if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
                raise ValueError(f"normalization hash for {intake_id} must be SHA-256")
            normalized[intake_id] = checksum
        return normalized


class OemBaselineAssemblyPreview(BaseModel):
    pack_id: str
    publication_id: str
    publication_revision_id: str
    base_intake_id: str
    temporary_revision_intake_ids: dict[str, str]
    task_count: int
    resource_count: int
    conflict_count: int
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    ready: bool


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _load_assembly_intakes(
    db: Session,
    *,
    pack: models.AircraftContentPack,
    intake_hashes: dict[str, str],
) -> tuple[
    models.AircraftOemPublication,
    models.AircraftOemPublicationRevision,
    list[backend_models.AircraftOemSourceIntake],
]:
    ids = list(intake_hashes)
    rows = (
        db.query(backend_models.AircraftOemSourceIntake)
        .filter(backend_models.AircraftOemSourceIntake.id.in_(ids))
        .all()
    )
    if len(rows) != len(ids):
        found = {row.id for row in rows}
        missing = sorted(set(ids) - found)
        raise HTTPException(
            status_code=404,
            detail="OEM source intake not found: " + ", ".join(missing),
        )
    for intake in rows:
        if intake.pack_id != pack.id:
            raise HTTPException(
                status_code=422,
                detail="Every assembly intake must belong to the selected content pack",
            )
        if intake.status not in {"APPROVED", "MATERIALIZED"}:
            raise HTTPException(
                status_code=409,
                detail=f"OEM source intake {intake.id} is not approved",
            )
        if intake.normalization_hash != intake_hashes[intake.id]:
            raise HTTPException(
                status_code=409,
                detail=f"OEM source intake {intake.id} changed after review",
            )
        blockers = [
            row
            for row in intake.rows
            if row.status in {"REVIEW_REQUIRED", "INVALID"}
        ]
        if blockers:
            raise HTTPException(
                status_code=409,
                detail=f"OEM source intake {intake.id} still has unresolved rows",
            )

    publication_ids = {row.publication_id for row in rows}
    revision_ids = {row.publication_revision_id for row in rows}
    if len(publication_ids) != 1 or len(revision_ids) != 1:
        raise HTTPException(
            status_code=422,
            detail="One assembled baseline cannot mix different OEM publications or base publication revisions",
        )
    publication = db.get(models.AircraftOemPublication, next(iter(publication_ids)))
    revision = db.get(models.AircraftOemPublicationRevision, next(iter(revision_ids)))
    if not publication or not revision:
        raise HTTPException(status_code=409, detail="OEM source lineage no longer resolves")
    if revision.publication_id != publication.id:
        raise HTTPException(status_code=409, detail="OEM publication lineage is inconsistent")
    if not governance._pack_matches_publication(pack, publication):
        raise HTTPException(
            status_code=422,
            detail="Content pack identity does not match the assembled OEM publication",
        )
    if publication.status != "ACTIVE" or revision.status != "CURRENT":
        raise HTTPException(
            status_code=409,
            detail="Assembly must use the active CURRENT OEM publication revision",
        )
    return publication, revision, rows


def _coverage(
    db: Session,
    *,
    publication: models.AircraftOemPublication,
    revision: models.AircraftOemPublicationRevision,
    intakes: list[backend_models.AircraftOemSourceIntake],
) -> tuple[backend_models.AircraftOemSourceIntake, dict[str, backend_models.AircraftOemSourceIntake]]:
    base = [row for row in intakes if row.temporary_revision_id is None]
    if len(base) != 1:
        raise HTTPException(
            status_code=409,
            detail="A complete OEM baseline assembly requires exactly one approved base-publication intake",
        )
    tr_intakes = {
        row.temporary_revision_id: row
        for row in intakes
        if row.temporary_revision_id is not None
    }
    if len(tr_intakes) != len([row for row in intakes if row.temporary_revision_id is not None]):
        raise HTTPException(
            status_code=409,
            detail="Only one approved intake may represent each active Temporary Revision in an assembly",
        )
    governed = governance.governed_publication_currentness(db, publication=publication)
    if governed.current_revision is None or governed.current_revision.id != revision.id:
        raise HTTPException(status_code=409, detail="OEM publication currentness changed")
    if governed.currentness_status not in {"CURRENT", "TEMPORARY_REVISION_ACTIVE"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "OEM source currentness must be resolved before baseline assembly: "
                + governed.currentness_status
            ),
        )
    required = {row.id for row in governed.active_temporary_revisions}
    supplied = set(tr_intakes)
    if supplied != required:
        missing = sorted(required - supplied)
        extra = sorted(supplied - required)
        detail = []
        if missing:
            detail.append("missing active Temporary Revision intakes: " + ", ".join(missing))
        if extra:
            detail.append("contains non-active Temporary Revision intakes: " + ", ".join(extra))
        raise HTTPException(status_code=409, detail="; ".join(detail))
    return base[0], tr_intakes


def _row_groups(
    intakes: list[backend_models.AircraftOemSourceIntake],
) -> dict[tuple[str, str], list[backend_models.AircraftOemSourceIntakeRow]]:
    groups: dict[
        tuple[str, str],
        list[backend_models.AircraftOemSourceIntakeRow],
    ] = defaultdict(list)
    for intake in intakes:
        for row in intake.rows:
            if row.status != "VALID" or row.row_kind not in {"TASK", "RESOURCE"}:
                continue
            identity = str(row.identity_key or "").strip()
            if not identity:
                raise HTTPException(
                    status_code=409,
                    detail=f"Valid {row.row_kind.lower()} row {row.id} has no controlled identity",
                )
            groups[(row.row_kind, identity)].append(row)
    return groups


def _resolution_map(
    resolutions: list[OemBaselineConflictResolution],
) -> dict[tuple[str, str], OemBaselineConflictResolution]:
    result: dict[tuple[str, str], OemBaselineConflictResolution] = {}
    for row in resolutions:
        key = (row.row_kind, row.identity_key)
        if key in result:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate conflict resolution for {row.row_kind}:{row.identity_key}",
            )
        result[key] = row
    return result


def _conflicts_and_selected(
    groups: dict[tuple[str, str], list[backend_models.AircraftOemSourceIntakeRow]],
    resolutions: list[OemBaselineConflictResolution],
) -> tuple[list[dict[str, Any]], list[backend_models.AircraftOemSourceIntakeRow]]:
    resolution_by_key = _resolution_map(resolutions)
    conflicts: list[dict[str, Any]] = []
    selected: list[backend_models.AircraftOemSourceIntakeRow] = []
    used_resolutions: set[tuple[str, str]] = set()
    for key, rows in sorted(groups.items()):
        if len(rows) == 1:
            selected.append(rows[0])
            continue
        normalized_variants = {_canonical(row.normalized_json) for row in rows}
        if len(normalized_variants) == 1:
            # Identical duplicate content still needs one deterministic source
            # row. Prefer an active TR over base because it is the later source
            # authority, then stable intake id for repeatability.
            selected.append(
                sorted(
                    rows,
                    key=lambda row: (
                        row.intake.temporary_revision_id is None,
                        row.intake_id,
                    ),
                )[0]
            )
            continue
        resolution = resolution_by_key.get(key)
        if resolution is None:
            conflicts.append(
                {
                    "row_kind": key[0],
                    "identity_key": key[1],
                    "candidate_intake_ids": sorted({row.intake_id for row in rows}),
                    "candidate_row_ids": sorted(row.id for row in rows),
                    "reason": "controlled content differs across base/TR sources",
                }
            )
            continue
        matching = [
            row for row in rows if row.intake_id == resolution.selected_intake_id
        ]
        if len(matching) != 1:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Resolution for {key[0]}:{key[1]} does not select exactly one candidate intake"
                ),
            )
        selected.append(matching[0])
        used_resolutions.add(key)

    unused = sorted(set(resolution_by_key) - used_resolutions)
    if unused:
        raise HTTPException(
            status_code=422,
            detail="Conflict resolutions were supplied for non-conflicting identities: "
            + ", ".join(f"{kind}:{identity}" for kind, identity in unused),
        )
    return conflicts, selected


def _source_for_intake(
    db: Session,
    *,
    intake: backend_models.AircraftOemSourceIntake,
    publication: models.AircraftOemPublication,
    revision: models.AircraftOemPublicationRevision,
) -> schemas.ContentSourceCreate:
    temporary = (
        db.get(models.AircraftOemTemporaryRevision, intake.temporary_revision_id)
        if intake.temporary_revision_id
        else None
    )
    reference, source_revision, checksum = backend_services._source_tuple(
        publication=publication,
        publication_revision=revision,
        temporary_revision=temporary,
    )
    return schemas.ContentSourceCreate(
        source_type="OEM_MPD",
        reference=reference,
        source_revision=source_revision,
        effective_date=(temporary.effective_date if temporary else revision.effective_date),
        checksum_sha256=checksum,
        authority=publication.manufacturer,
        provenance_json={
            "publication_id": publication.id,
            "publication_revision_id": revision.id,
            "temporary_revision_id": temporary.id if temporary else None,
            "source_intake_id": intake.id,
            "source_filename": intake.source_filename,
            "storage_locator": intake.storage_locator,
            "normalization_hash": intake.normalization_hash,
            "source_manifest": intake.source_manifest_json,
            "provenance_basis": "GOVERNED_OEM_BASELINE_ASSEMBLY",
        },
        publication_revision_id=revision.id,
        temporary_revision_id=temporary.id if temporary else None,
        document_locator=intake.storage_locator
        or (temporary.storage_locator if temporary else revision.storage_locator)
        or (temporary.source_url if temporary else revision.source_url),
    )


def preview_assembly(
    db: Session,
    *,
    pack: models.AircraftContentPack,
    payload: OemBaselineAssemblyCreate,
) -> tuple[
    OemBaselineAssemblyPreview,
    models.AircraftOemPublication,
    models.AircraftOemPublicationRevision,
    list[backend_models.AircraftOemSourceIntake],
    list[backend_models.AircraftOemSourceIntakeRow],
]:
    publication, revision, intakes = _load_assembly_intakes(
        db,
        pack=pack,
        intake_hashes=payload.intake_hashes,
    )
    base, tr_intakes = _coverage(
        db,
        publication=publication,
        revision=revision,
        intakes=intakes,
    )
    groups = _row_groups(intakes)
    conflicts, selected = _conflicts_and_selected(groups, payload.conflict_resolutions)
    preview = OemBaselineAssemblyPreview(
        pack_id=pack.id,
        publication_id=publication.id,
        publication_revision_id=revision.id,
        base_intake_id=base.id,
        temporary_revision_intake_ids={
            tr_id: intake.id for tr_id, intake in sorted(tr_intakes.items())
        },
        task_count=sum(1 for row in selected if row.row_kind == "TASK"),
        resource_count=sum(1 for row in selected if row.row_kind == "RESOURCE"),
        conflict_count=len(conflicts),
        conflicts=conflicts,
        ready=not conflicts,
    )
    return preview, publication, revision, intakes, selected


def create_assembled_revision(
    db: Session,
    *,
    pack: models.AircraftContentPack,
    payload: OemBaselineAssemblyCreate,
    user: account_models.User,
) -> models.AircraftContentPackRevision:
    governance.require_platform_human(user)
    legacy_services._advisory_lock(db, f"aircraft-oem-baseline-assembly:{pack.id}")
    preview, publication, publication_revision, intakes, selected = preview_assembly(
        db,
        pack=pack,
        payload=payload,
    )
    if not preview.ready:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "OEM baseline assembly contains unresolved controlled-content conflicts",
                "conflicts": preview.conflicts,
            },
        )
    sources = [
        _source_for_intake(
            db,
            intake=intake,
            publication=publication,
            revision=publication_revision,
        )
        for intake in sorted(
            intakes,
            key=lambda row: (row.temporary_revision_id is not None, row.temporary_revision_id or ""),
        )
    ]
    tasks = [
        schemas.ContentTaskCreate.model_validate(row.normalized_json)
        for row in selected
        if row.row_kind == "TASK"
    ]
    resources = [
        schemas.ContentResourceCreate.model_validate(row.normalized_json)
        for row in selected
        if row.row_kind == "RESOURCE"
    ]
    content = schemas.ContentRevisionCreate(
        revision_code=payload.revision_code,
        change_summary=payload.change_summary
        or (
            f"Assembled governed OEM baseline from base intake {preview.base_intake_id} "
            f"and {len(preview.temporary_revision_intake_ids)} active Temporary Revision intake(s)"
        ),
        sources=sources,
        tasks=tasks,
        resources=resources,
    )
    revision = legacy_services.create_revision(
        db,
        pack=pack,
        payload=content,
        user=user,
    )
    # create_revision commits. Append the assembly audit as a second immutable
    # audit transaction so provenance still records every reviewed input/hash.
    governance._audit(
        db,
        user=user,
        entity_type="AIRCRAFT_CONTENT_PACK_REVISION",
        entity_id=revision.id,
        action="ASSEMBLE_OEM_BASELINE",
        after={
            "pack_id": pack.id,
            "publication_id": publication.id,
            "publication_revision_id": publication_revision.id,
            "base_intake_id": preview.base_intake_id,
            "temporary_revision_intake_ids": preview.temporary_revision_intake_ids,
            "intake_hashes": payload.intake_hashes,
            "task_count": preview.task_count,
            "resource_count": preview.resource_count,
            "conflict_resolutions": [
                item.model_dump(mode="json") for item in payload.conflict_resolutions
            ],
        },
        critical=True,
    )
    db.commit()
    db.refresh(revision)
    return revision
