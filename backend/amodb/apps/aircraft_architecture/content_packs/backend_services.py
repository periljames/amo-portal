from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import (
    backend_ingestion,
    backend_models,
    backend_schemas,
    governance,
    models,
    schemas,
    services as legacy_services,
)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _intake_hash(
    intake: backend_models.AircraftOemSourceIntake,
    rows: Iterable[backend_models.AircraftOemSourceIntakeRow] | None = None,
) -> str:
    rows = list(rows if rows is not None else intake.rows)
    return _canonical_hash(
        {
            "publication_id": intake.publication_id,
            "publication_revision_id": intake.publication_revision_id,
            "temporary_revision_id": intake.temporary_revision_id,
            "pack_id": intake.pack_id,
            "checksum_sha256": intake.checksum_sha256,
            "profile": intake.detected_profile,
            "rows": [
                {
                    "sheet_name": row.sheet_name,
                    "row_number": row.row_number,
                    "row_kind": row.row_kind,
                    "identity_key": row.identity_key,
                    "row_hash": row.row_hash,
                    "status": row.status,
                }
                for row in sorted(rows, key=lambda item: (item.sheet_name, item.row_number))
            ],
        }
    )


def _source_tuple(
    *,
    publication: models.AircraftOemPublication,
    publication_revision: models.AircraftOemPublicationRevision,
    temporary_revision: models.AircraftOemTemporaryRevision | None,
) -> tuple[str, str, str]:
    return (
        publication.publication_code,
        (
            temporary_revision.temporary_revision_code
            if temporary_revision is not None
            else publication_revision.revision_code
        ),
        (
            temporary_revision.checksum_sha256
            if temporary_revision is not None
            else publication_revision.checksum_sha256
        ),
    )


def _load_binding(
    db: Session,
    *,
    binding: backend_schemas.IntakeSourceBinding,
) -> tuple[
    models.AircraftOemPublication,
    models.AircraftOemPublicationRevision,
    models.AircraftOemTemporaryRevision | None,
    models.AircraftContentPack,
]:
    publication = db.get(models.AircraftOemPublication, binding.publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="OEM publication not found")
    revision = db.get(
        models.AircraftOemPublicationRevision,
        binding.publication_revision_id,
    )
    if not revision or revision.publication_id != publication.id:
        raise HTTPException(
            status_code=422,
            detail="OEM publication revision does not belong to the selected publication",
        )
    temporary = None
    if binding.temporary_revision_id:
        temporary = db.get(
            models.AircraftOemTemporaryRevision,
            binding.temporary_revision_id,
        )
        if not temporary or temporary.publication_revision_id != revision.id:
            raise HTTPException(
                status_code=422,
                detail="Temporary Revision does not belong to the selected publication revision",
            )
    pack = db.get(models.AircraftContentPack, binding.pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Content pack not found")
    if not governance._pack_matches_publication(pack, publication):
        raise HTTPException(
            status_code=422,
            detail="Content pack identity does not match the selected OEM publication",
        )
    return publication, revision, temporary, pack


def _intake_for_user(
    db: Session,
    *,
    intake_id: str,
    user: account_models.User,
    for_update: bool = False,
) -> backend_models.AircraftOemSourceIntake:
    governance.require_source_contributor(user)
    query = db.query(backend_models.AircraftOemSourceIntake).filter(
        backend_models.AircraftOemSourceIntake.id == intake_id
    )
    if for_update:
        query = query.with_for_update(of=backend_models.AircraftOemSourceIntake)
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="OEM source intake not found")
    if not bool(getattr(user, "is_superuser", False)):
        if row.submitted_by_amo_id != getattr(user, "amo_id", None):
            raise HTTPException(status_code=404, detail="OEM source intake not found")
    return row


def stage_intake(
    db: Session,
    *,
    filename: str,
    content: bytes,
    binding: backend_schemas.IntakeSourceBinding,
    user: account_models.User,
) -> backend_models.AircraftOemSourceIntake:
    governance.require_source_contributor(user)
    publication, revision, temporary, pack = _load_binding(db, binding=binding)
    if publication.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="OEM publication is inactive")
    if revision.status not in {"CANDIDATE", "VERIFIED", "CURRENT"}:
        raise HTTPException(
            status_code=409,
            detail="Source intake requires a candidate, verified, or current OEM publication revision",
        )
    if temporary is not None and temporary.status not in {"CANDIDATE", "ACTIVE"}:
        raise HTTPException(
            status_code=409,
            detail="Source intake cannot use a closed Temporary Revision",
        )

    checksum = hashlib.sha256(content).hexdigest()
    expected_checksum = (
        temporary.checksum_sha256 if temporary is not None else revision.checksum_sha256
    )
    if checksum != expected_checksum:
        raise HTTPException(
            status_code=422,
            detail=(
                "Uploaded source checksum does not match the controlled OEM publication "
                "revision/Temporary Revision record"
            ),
        )

    source_reference, source_revision, source_checksum = _source_tuple(
        publication=publication,
        publication_revision=revision,
        temporary_revision=temporary,
    )
    try:
        preview, candidates = backend_ingestion.normalize_oem_workbook(
            filename=filename,
            content=content,
            source_reference=source_reference,
            source_revision=source_revision,
            source_checksum_sha256=source_checksum,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if preview.recommended_pack_code and preview.recommended_pack_code != pack.code:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Workbook profile recommends {preview.recommended_pack_code}; selected pack is {pack.code}"
            ),
        )

    legacy_services._advisory_lock(
        db,
        f"aircraft-oem-source-intake:{publication.id}:{checksum}",
    )
    duplicate = db.query(backend_models.AircraftOemSourceIntake).filter(
        backend_models.AircraftOemSourceIntake.publication_id == publication.id,
        backend_models.AircraftOemSourceIntake.checksum_sha256 == checksum,
    ).first()
    if duplicate:
        same_binding = (
            duplicate.publication_revision_id == revision.id
            and duplicate.temporary_revision_id == (temporary.id if temporary else None)
            and duplicate.pack_id == pack.id
        )
        if same_binding:
            return duplicate
        raise HTTPException(
            status_code=409,
            detail="The same OEM source checksum is already staged against a different controlled binding",
        )

    row = backend_models.AircraftOemSourceIntake(
        publication_id=publication.id,
        publication_revision_id=revision.id,
        temporary_revision_id=temporary.id if temporary else None,
        pack_id=pack.id,
        submitted_by_amo_id=getattr(user, "amo_id", None),
        source_filename=preview.filename,
        storage_locator=binding.storage_locator
        or (temporary.storage_locator if temporary else revision.storage_locator),
        checksum_sha256=preview.checksum_sha256,
        size_bytes=preview.size_bytes,
        detected_profile=preview.detected_profile,
        profile_confidence=preview.profile_confidence,
        workbook_kind=preview.workbook_kind,
        status="STAGED",
        source_manifest_json=preview.source_manifest,
        warnings_json=preview.warnings,
        validation_summary_json={},
        created_by_user_id=user.id,
    )
    db.add(row)
    db.flush()
    for candidate in candidates:
        db.add(
            backend_models.AircraftOemSourceIntakeRow(
                intake_id=row.id,
                sheet_name=candidate.sheet_name,
                row_number=candidate.row_number,
                row_kind=candidate.row_kind,
                identity_key=candidate.identity_key,
                row_hash=candidate.row_hash,
                source_json=candidate.source_json,
                normalized_json=candidate.normalized_json,
                status=candidate.status,
                issues_json=candidate.issues,
            )
        )
    db.flush()
    row.normalization_hash = _intake_hash(row)
    db.add(row)
    governance._audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_SOURCE_INTAKE",
        entity_id=row.id,
        action="STAGE",
        after={
            "publication_id": publication.id,
            "publication_revision_id": revision.id,
            "temporary_revision_id": temporary.id if temporary else None,
            "pack_id": pack.id,
            "checksum_sha256": checksum,
            "profile": preview.detected_profile,
            "row_count": len(candidates),
        },
        critical=False,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="OEM source intake conflicts with an existing staged source",
        ) from exc
    db.refresh(row)
    return row


def _candidate_identity_duplicates(
    rows: list[backend_models.AircraftOemSourceIntakeRow],
) -> dict[tuple[str, str], list[backend_models.AircraftOemSourceIntakeRow]]:
    grouped: dict[
        tuple[str, str],
        list[backend_models.AircraftOemSourceIntakeRow],
    ] = {}
    for row in rows:
        if row.status == "IGNORED" or row.row_kind not in {"TASK", "RESOURCE"}:
            continue
        key = (row.row_kind, str(row.identity_key or "").strip())
        if key[1]:
            grouped.setdefault(key, []).append(row)
    return {key: value for key, value in grouped.items() if len(value) > 1}


def validate_intake(
    db: Session,
    *,
    intake_id: str,
    user: account_models.User,
) -> backend_schemas.OemSourceIntakeValidateRead:
    intake = _intake_for_user(
        db,
        intake_id=intake_id,
        user=user,
        for_update=True,
    )
    if intake.status not in {"STAGED", "VALIDATED"}:
        raise HTTPException(
            status_code=409,
            detail="Only staged source intake can be validated",
        )
    rows = list(intake.rows)
    duplicates = _candidate_identity_duplicates(rows)
    duplicate_ids = {row.id for group in duplicates.values() for row in group}
    if duplicate_ids:
        for row in rows:
            if row.id not in duplicate_ids:
                continue
            issues = list(row.issues_json or [])
            if not any(issue.get("code") == "DUPLICATE_CONTROLLED_IDENTITY" for issue in issues):
                issues.append(
                    {
                        "code": "DUPLICATE_CONTROLLED_IDENTITY",
                        "message": (
                            f"Duplicate {row.row_kind.lower()} identity {row.identity_key} "
                            "must be reconciled before approval"
                        ),
                    }
                )
            row.issues_json = issues
            row.status = "INVALID"
            row.row_hash = _canonical_hash(
                {
                    "sheet_name": row.sheet_name,
                    "row_number": row.row_number,
                    "row_kind": row.row_kind,
                    "source_json": row.source_json,
                    "normalized_json": row.normalized_json,
                    "status": row.status,
                    "issues": row.issues_json,
                }
            )
            db.add(row)

    totals = {
        "VALID": 0,
        "REVIEW_REQUIRED": 0,
        "INVALID": 0,
        "IGNORED": 0,
    }
    task_rows = 0
    resource_rows = 0
    for row in rows:
        totals[row.status] = totals.get(row.status, 0) + 1
        if row.status != "IGNORED" and row.row_kind == "TASK":
            task_rows += 1
        elif row.status != "IGNORED" and row.row_kind == "RESOURCE":
            resource_rows += 1

    if task_rows == 0:
        totals["INVALID"] += 1
    blockers = totals["REVIEW_REQUIRED"] + totals["INVALID"]
    intake.status = "VALIDATED" if blockers == 0 and task_rows > 0 else "STAGED"
    intake.validated_at = (
        datetime.now(timezone.utc) if intake.status == "VALIDATED" else None
    )
    intake.validation_summary_json = {
        "total_rows": len(rows),
        "valid_rows": totals["VALID"],
        "review_required_rows": totals["REVIEW_REQUIRED"],
        "invalid_rows": totals["INVALID"],
        "ignored_rows": totals["IGNORED"],
        "task_rows": task_rows,
        "resource_rows": resource_rows,
        "duplicate_identities": [f"{kind}:{identity}" for kind, identity in duplicates],
        "no_controlled_tasks": task_rows == 0,
    }
    intake.normalization_hash = _intake_hash(intake, rows)
    db.add(intake)
    governance._audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_SOURCE_INTAKE",
        entity_id=intake.id,
        action="VALIDATE",
        after={
            "status": intake.status,
            "normalization_hash": intake.normalization_hash,
            **intake.validation_summary_json,
        },
    )
    db.commit()
    db.refresh(intake)
    return backend_schemas.OemSourceIntakeValidateRead(
        intake_id=intake.id,
        status=intake.status,
        normalization_hash=intake.normalization_hash,
        total_rows=len(rows),
        valid_rows=totals["VALID"],
        review_required_rows=totals["REVIEW_REQUIRED"],
        invalid_rows=totals["INVALID"],
        ignored_rows=totals["IGNORED"],
        task_rows=task_rows,
        resource_rows=resource_rows,
    )


def _validate_corrected_row(
    *,
    row: backend_models.AircraftOemSourceIntakeRow,
    normalized_json: dict[str, Any],
    source_tuple: tuple[str, str, str],
) -> dict[str, Any]:
    source_reference, source_revision, checksum = source_tuple
    if row.row_kind == "TASK":
        validated = schemas.ContentTaskCreate.model_validate(normalized_json)
        if (
            validated.source_reference,
            validated.source_revision,
            validated.source_checksum_sha256,
        ) != source_tuple:
            raise HTTPException(
                status_code=422,
                detail="Corrected task cannot change the controlled source tuple",
            )
        governance._validate_effectivity(validated)
        return validated.model_dump(mode="json")
    if row.row_kind == "RESOURCE":
        validated = schemas.ContentResourceCreate.model_validate(normalized_json)
        if (
            validated.source_reference,
            validated.source_revision,
            validated.source_checksum_sha256,
        ) != source_tuple:
            raise HTTPException(
                status_code=422,
                detail="Corrected resource cannot change the controlled source tuple",
            )
        return validated.model_dump(mode="json")
    raise HTTPException(
        status_code=409,
        detail="Only task or resource candidate rows can be corrected",
    )


def resolve_intake_row(
    db: Session,
    *,
    row_id: str,
    payload: backend_schemas.OemSourceIntakeRowResolution,
    user: account_models.User,
) -> backend_models.AircraftOemSourceIntakeRow:
    governance.require_source_contributor(user)
    row = (
        db.query(backend_models.AircraftOemSourceIntakeRow)
        .filter(backend_models.AircraftOemSourceIntakeRow.id == row_id)
        .with_for_update(of=backend_models.AircraftOemSourceIntakeRow)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="OEM source intake row not found")
    intake = row.intake
    if not bool(getattr(user, "is_superuser", False)) and (
        intake.submitted_by_amo_id != getattr(user, "amo_id", None)
    ):
        raise HTTPException(status_code=404, detail="OEM source intake row not found")
    if intake.status not in {"STAGED", "VALIDATED"}:
        raise HTTPException(
            status_code=409,
            detail="Rows cannot be changed after source intake approval",
        )

    publication = db.get(models.AircraftOemPublication, intake.publication_id)
    publication_revision = db.get(
        models.AircraftOemPublicationRevision,
        intake.publication_revision_id,
    )
    temporary = (
        db.get(models.AircraftOemTemporaryRevision, intake.temporary_revision_id)
        if intake.temporary_revision_id
        else None
    )
    source_tuple = _source_tuple(
        publication=publication,
        publication_revision=publication_revision,
        temporary_revision=temporary,
    )
    before = {
        "status": row.status,
        "row_kind": row.row_kind,
        "row_hash": row.row_hash,
    }
    if payload.action == "CORRECT":
        try:
            row.normalized_json = _validate_corrected_row(
                row=row,
                normalized_json=payload.normalized_json or {},
                source_tuple=source_tuple,
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=exc.errors(include_url=False),
            ) from exc
        row.status = "VALID"
        row.issues_json = []
    elif payload.action == "ACCEPT":
        if row.issues_json:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A row with unresolved import issues cannot be accepted without a controlled correction; use CORRECT or IGNORE"
                ),
            )
        _validate_corrected_row(
            row=row,
            normalized_json=row.normalized_json,
            source_tuple=source_tuple,
        )
        row.status = "VALID"
    elif payload.action == "IGNORE":
        row.status = "IGNORED"
        row.row_kind = "IGNORED"
    elif payload.action == "REJECT":
        row.status = "INVALID"

    now = datetime.now(timezone.utc)
    row.review_json = {
        "action": payload.action,
        "rationale": payload.rationale,
        "actor_user_id": user.id,
        "at": now.isoformat(),
    }
    row.reviewed_by_user_id = user.id
    row.reviewed_at = now
    row.row_hash = _canonical_hash(
        {
            "sheet_name": row.sheet_name,
            "row_number": row.row_number,
            "row_kind": row.row_kind,
            "source_json": row.source_json,
            "normalized_json": row.normalized_json,
            "status": row.status,
            "issues": row.issues_json,
            "review": row.review_json,
        }
    )
    intake.status = "STAGED"
    intake.validated_at = None
    db.add(row)
    db.add(intake)
    db.flush()
    intake.normalization_hash = _intake_hash(intake)
    db.add(intake)
    governance._audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_SOURCE_INTAKE_ROW",
        entity_id=row.id,
        action=payload.action,
        before=before,
        after={
            "status": row.status,
            "row_kind": row.row_kind,
            "row_hash": row.row_hash,
        },
        metadata={"rationale": payload.rationale, "intake_id": intake.id},
        critical=payload.action in {"CORRECT", "IGNORE", "REJECT"},
    )
    db.commit()
    db.refresh(row)
    return row


def _assert_intake_source_current(
    db: Session,
    intake: backend_models.AircraftOemSourceIntake,
) -> tuple[
    models.AircraftOemPublication,
    models.AircraftOemPublicationRevision,
    models.AircraftOemTemporaryRevision | None,
    models.AircraftContentPack,
]:
    publication = db.get(models.AircraftOemPublication, intake.publication_id)
    revision = db.get(
        models.AircraftOemPublicationRevision,
        intake.publication_revision_id,
    )
    temporary = (
        db.get(models.AircraftOemTemporaryRevision, intake.temporary_revision_id)
        if intake.temporary_revision_id
        else None
    )
    pack = db.get(models.AircraftContentPack, intake.pack_id)
    if not publication or not revision or not pack:
        raise HTTPException(
            status_code=409,
            detail="Controlled source binding is incomplete",
        )
    if publication.status != "ACTIVE" or revision.status != "CURRENT":
        raise HTTPException(
            status_code=409,
            detail="OEM source intake can only be approved against the CURRENT active publication revision",
        )
    if not governance._pack_matches_publication(pack, publication):
        raise HTTPException(
            status_code=409,
            detail="Content pack no longer matches the OEM publication identity",
        )
    if temporary is not None and (
        temporary.publication_revision_id != revision.id
        or temporary.status != "ACTIVE"
        or temporary.verified_at is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Bound Temporary Revision is not active and verified",
        )
    expected = temporary.checksum_sha256 if temporary else revision.checksum_sha256
    if expected != intake.checksum_sha256:
        raise HTTPException(
            status_code=409,
            detail="Controlled source checksum changed after intake",
        )
    currentness = governance.governed_publication_currentness(
        db,
        publication=publication,
    )
    if currentness.currentness_status not in {
        "CURRENT",
        "TEMPORARY_REVISION_ACTIVE",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "OEM source currentness requires resolution before content approval: "
                + currentness.currentness_status
            ),
        )
    return publication, revision, temporary, pack


def approve_intake(
    db: Session,
    *,
    intake_id: str,
    payload: backend_schemas.OemSourceIntakeApproval,
    user: account_models.User,
) -> backend_models.AircraftOemSourceIntake:
    governance.require_platform_human(user)
    intake = (
        db.query(backend_models.AircraftOemSourceIntake)
        .filter(backend_models.AircraftOemSourceIntake.id == intake_id)
        .with_for_update(of=backend_models.AircraftOemSourceIntake)
        .first()
    )
    if not intake:
        raise HTTPException(status_code=404, detail="OEM source intake not found")
    if intake.status != "VALIDATED":
        raise HTTPException(
            status_code=409,
            detail="OEM source intake must be validated before approval",
        )
    if payload.expected_normalization_hash != intake.normalization_hash:
        raise HTTPException(
            status_code=409,
            detail="Normalized OEM content changed after review",
        )
    _assert_intake_source_current(db, intake)
    blockers = [
        row
        for row in intake.rows
        if row.status in {"REVIEW_REQUIRED", "INVALID"}
    ]
    if blockers:
        raise HTTPException(
            status_code=409,
            detail="Unresolved source intake rows block approval",
        )
    now = datetime.now(timezone.utc)
    summary = dict(intake.validation_summary_json or {})
    summary["approval_note"] = payload.approval_note
    summary["approved_by_user_id"] = user.id
    summary["approved_at"] = now.isoformat()
    intake.validation_summary_json = summary
    intake.status = "APPROVED"
    intake.approved_by_user_id = user.id
    intake.approved_at = now
    db.add(intake)
    governance._audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_SOURCE_INTAKE",
        entity_id=intake.id,
        action="APPROVE",
        before={"status": "VALIDATED"},
        after={
            "status": "APPROVED",
            "normalization_hash": intake.normalization_hash,
        },
        metadata={"approval_note": payload.approval_note},
        critical=True,
    )
    db.commit()
    db.refresh(intake)
    return intake


def _materialization_payload(
    *,
    intake: backend_models.AircraftOemSourceIntake,
    publication: models.AircraftOemPublication,
    publication_revision: models.AircraftOemPublicationRevision,
    temporary: models.AircraftOemTemporaryRevision | None,
    revision_code: str,
    change_summary: str | None,
) -> schemas.ContentRevisionCreate:
    source_reference, source_revision, checksum = _source_tuple(
        publication=publication,
        publication_revision=publication_revision,
        temporary_revision=temporary,
    )
    source = schemas.ContentSourceCreate(
        source_type="OEM_MPD",
        reference=source_reference,
        source_revision=source_revision,
        effective_date=(
            temporary.effective_date if temporary else publication_revision.effective_date
        ),
        checksum_sha256=checksum,
        authority=publication.manufacturer,
        provenance_json={
            "publication_id": publication.id,
            "publication_revision_id": publication_revision.id,
            "temporary_revision_id": temporary.id if temporary else None,
            "source_intake_id": intake.id,
            "source_filename": intake.source_filename,
            "storage_locator": intake.storage_locator,
            "source_manifest": intake.source_manifest_json,
            "normalization_hash": intake.normalization_hash,
            "provenance_basis": "GOVERNED_OEM_SOURCE_INTAKE",
        },
        publication_revision_id=publication_revision.id,
        temporary_revision_id=temporary.id if temporary else None,
        document_locator=intake.storage_locator
        or (temporary.storage_locator if temporary else publication_revision.storage_locator)
        or (temporary.source_url if temporary else publication_revision.source_url),
    )
    tasks: list[schemas.ContentTaskCreate] = []
    resources: list[schemas.ContentResourceCreate] = []
    for row in sorted(intake.rows, key=lambda item: (item.sheet_name, item.row_number)):
        if row.status != "VALID":
            continue
        if row.row_kind == "TASK":
            tasks.append(schemas.ContentTaskCreate.model_validate(row.normalized_json))
        elif row.row_kind == "RESOURCE":
            resources.append(
                schemas.ContentResourceCreate.model_validate(row.normalized_json)
            )
    return schemas.ContentRevisionCreate(
        revision_code=revision_code,
        change_summary=change_summary
        or f"Materialized from governed OEM source intake {intake.id}",
        sources=[source],
        tasks=tasks,
        resources=resources,
    )


def materialize_intake(
    db: Session,
    *,
    intake_id: str,
    payload: backend_schemas.OemSourceIntakeMaterialize,
    user: account_models.User,
) -> models.AircraftContentPackRevision:
    governance.require_platform_human(user)
    legacy_services._advisory_lock(
        db,
        f"aircraft-oem-intake-materialize:{intake_id}",
    )
    intake = (
        db.query(backend_models.AircraftOemSourceIntake)
        .filter(backend_models.AircraftOemSourceIntake.id == intake_id)
        .with_for_update(of=backend_models.AircraftOemSourceIntake)
        .first()
    )
    if not intake:
        raise HTTPException(status_code=404, detail="OEM source intake not found")
    if intake.status == "MATERIALIZED" and intake.materialized_revision_id:
        existing = db.get(
            models.AircraftContentPackRevision,
            intake.materialized_revision_id,
        )
        if existing:
            return existing
    if intake.status != "APPROVED":
        raise HTTPException(
            status_code=409,
            detail="OEM source intake must be approved before materialization",
        )
    if payload.expected_normalization_hash != intake.normalization_hash:
        raise HTTPException(
            status_code=409,
            detail="Normalized OEM content changed after approval",
        )
    publication, publication_revision, temporary, pack = _assert_intake_source_current(
        db,
        intake,
    )
    content_payload = _materialization_payload(
        intake=intake,
        publication=publication,
        publication_revision=publication_revision,
        temporary=temporary,
        revision_code=payload.revision_code,
        change_summary=payload.change_summary,
    )
    governance.validate_source_backing(
        content_payload,
        db=db,
        pack=pack,
        for_publication=False,
    )
    duplicate = db.query(models.AircraftContentPackRevision.id).filter(
        models.AircraftContentPackRevision.pack_id == pack.id,
        models.AircraftContentPackRevision.revision_code == payload.revision_code,
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="Content-pack revision code already exists",
        )

    revision = models.AircraftContentPackRevision(
        pack_id=pack.id,
        revision_code=content_payload.revision_code,
        change_summary=content_payload.change_summary,
        content_hash=legacy_services.revision_hash(pack, content_payload),
        created_by_user_id=user.id,
    )
    db.add(revision)
    db.flush()
    for source in content_payload.sources:
        db.add(
            models.AircraftContentPackSource(
                revision_id=revision.id,
                **source.model_dump(),
            )
        )
    for task in content_payload.tasks:
        db.add(
            models.AircraftContentPackTask(
                revision_id=revision.id,
                **task.model_dump(),
            )
        )
    for resource in content_payload.resources:
        db.add(
            models.AircraftContentPackResource(
                revision_id=revision.id,
                **resource.model_dump(),
            )
        )
    now = datetime.now(timezone.utc)
    intake.status = "MATERIALIZED"
    intake.materialized_revision_id = revision.id
    intake.materialized_at = now
    db.add(intake)
    governance._audit(
        db,
        user=user,
        entity_type="AIRCRAFT_CONTENT_PACK_REVISION",
        entity_id=revision.id,
        action="MATERIALIZE_DRAFT",
        after={
            "pack_id": pack.id,
            "revision_code": revision.revision_code,
            "content_hash": revision.content_hash,
            "source_intake_id": intake.id,
            "task_count": len(content_payload.tasks),
            "resource_count": len(content_payload.resources),
        },
        critical=True,
    )
    governance._audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_SOURCE_INTAKE",
        entity_id=intake.id,
        action="MATERIALIZE",
        before={"status": "APPROVED"},
        after={
            "status": "MATERIALIZED",
            "materialized_revision_id": revision.id,
        },
        critical=True,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="OEM source materialization conflicts with existing controlled content",
        ) from exc
    db.refresh(revision)
    return revision


def list_intakes(
    db: Session,
    *,
    user: account_models.User,
    status: str | None,
    publication_id: str | None,
    offset: int,
    limit: int,
) -> tuple[int, list[backend_models.AircraftOemSourceIntake]]:
    governance.require_source_contributor(user)
    query = db.query(backend_models.AircraftOemSourceIntake)
    if not bool(getattr(user, "is_superuser", False)):
        query = query.filter(
            backend_models.AircraftOemSourceIntake.submitted_by_amo_id
            == getattr(user, "amo_id", None)
        )
    if status:
        query = query.filter(backend_models.AircraftOemSourceIntake.status == status)
    if publication_id:
        query = query.filter(
            backend_models.AircraftOemSourceIntake.publication_id == publication_id
        )
    total = query.count()
    rows = (
        query.order_by(backend_models.AircraftOemSourceIntake.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, rows


def get_intake(
    db: Session,
    *,
    intake_id: str,
    user: account_models.User,
) -> backend_models.AircraftOemSourceIntake:
    return _intake_for_user(db, intake_id=intake_id, user=user)


def list_intake_rows(
    db: Session,
    *,
    intake_id: str,
    user: account_models.User,
    status: str | None,
    row_kind: str | None,
    offset: int,
    limit: int,
) -> tuple[int, list[backend_models.AircraftOemSourceIntakeRow]]:
    intake = _intake_for_user(db, intake_id=intake_id, user=user)
    query = db.query(backend_models.AircraftOemSourceIntakeRow).filter(
        backend_models.AircraftOemSourceIntakeRow.intake_id == intake.id
    )
    if status:
        query = query.filter(backend_models.AircraftOemSourceIntakeRow.status == status)
    if row_kind:
        query = query.filter(
            backend_models.AircraftOemSourceIntakeRow.row_kind == row_kind
        )
    total = query.count()
    rows = (
        query.order_by(
            backend_models.AircraftOemSourceIntakeRow.sheet_name,
            backend_models.AircraftOemSourceIntakeRow.row_number,
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, rows


def full_revision(
    revision: models.AircraftContentPackRevision,
) -> backend_schemas.ContentRevisionFullRead:
    return backend_schemas.ContentRevisionFullRead(
        **schemas.ContentRevisionRead.model_validate(revision).model_dump(),
        sources=[schemas.ContentSourceRead.model_validate(row) for row in revision.sources],
        positions=[
            backend_schemas.ContentPositionFullRead.model_validate(row)
            for row in revision.positions
        ],
        components=[
            backend_schemas.ContentComponentFullRead.model_validate(row)
            for row in revision.components
        ],
        tasks=[schemas.ContentTaskRead.model_validate(row) for row in revision.tasks],
        resources=[
            schemas.ContentResourceRead.model_validate(row) for row in revision.resources
        ],
    )


def paginated_revision_entities(
    revision: models.AircraftContentPackRevision,
    *,
    entity: str,
    offset: int,
    limit: int,
) -> tuple[int, list[dict[str, Any]]]:
    if entity == "tasks":
        rows = sorted(revision.tasks, key=lambda row: row.task_code)
        serialize = lambda row: schemas.ContentTaskRead.model_validate(row).model_dump(mode="json")
    elif entity == "resources":
        rows = sorted(revision.resources, key=lambda row: (row.resource_kind, row.resource_code))
        serialize = lambda row: schemas.ContentResourceRead.model_validate(row).model_dump(mode="json")
    elif entity == "positions":
        rows = sorted(revision.positions, key=lambda row: row.code)
        serialize = lambda row: backend_schemas.ContentPositionFullRead.model_validate(row).model_dump(mode="json")
    elif entity == "components":
        rows = sorted(revision.components, key=lambda row: row.definition_code)
        serialize = lambda row: backend_schemas.ContentComponentFullRead.model_validate(row).model_dump(mode="json")
    else:
        raise ValueError(f"Unsupported content entity: {entity}")
    return len(rows), [serialize(row) for row in rows[offset : offset + limit]]
