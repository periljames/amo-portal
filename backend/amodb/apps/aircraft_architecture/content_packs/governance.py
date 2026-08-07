from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.aircraft_architecture.effectivity.evaluator import evaluate_expression
from amodb.apps.audit import services as audit_services

from . import backend_schemas, models, schemas


WATCH_RESULT_CODES = {
    "OK",
    "CHANGE_DETECTED",
    "ERROR",
    "AUTH_REQUIRED",
    "UNAVAILABLE",
}
UNIVERSAL_EFFECTIVITY = {
    "ALL",
    "ALL A/C",
    "ALL AC",
    "ALL AIRCRAFT",
    "ALL AIRPLANES",
    "ALL MSN",
}

_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}


def _same_text(left: str | None, right: str | None) -> bool:
    return (left or "").strip().casefold() == (right or "").strip().casefold()


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


def _require_active_human(user: account_models.User) -> None:
    if not bool(getattr(user, "is_active", False)) or bool(
        getattr(user, "is_system_account", False)
    ):
        raise HTTPException(status_code=403, detail="An active human account is required")


def require_source_contributor(user: account_models.User) -> None:
    _require_active_human(user)
    if not (
        bool(getattr(user, "is_superuser", False))
        or bool(getattr(user, "is_amo_admin", False))
    ):
        raise HTTPException(
            status_code=403,
            detail="Platform superuser or AMO administrator authority is required",
        )


def require_platform_human(user: account_models.User) -> None:
    _require_active_human(user)
    if not bool(getattr(user, "is_superuser", False)):
        raise HTTPException(status_code=403, detail="Platform superuser authority is required")


def _pack_matches_publication(
    pack: models.AircraftContentPack,
    publication: models.AircraftOemPublication,
) -> bool:
    return (
        _same_text(pack.manufacturer, publication.manufacturer)
        and _same_text(pack.family, publication.family)
        and _same_text(pack.series, publication.series)
    )


def _source_candidates(
    payload: schemas.ContentRevisionCreate,
    source_reference: str,
) -> list[schemas.ContentSourceCreate]:
    return [row for row in payload.sources if row.reference == source_reference]


def _bound_metadata(
    *,
    payload: schemas.ContentRevisionCreate,
    source_reference: str,
    metadata_json: dict[str, Any],
    entity_label: str,
) -> dict[str, Any]:
    metadata = dict(metadata_json or {})
    candidates = _source_candidates(payload, source_reference)
    if not candidates:
        raise HTTPException(
            status_code=422,
            detail=f"{entity_label} has no matching controlled source",
        )
    requested_revision = str(metadata.get("source_revision") or "").strip()
    requested_checksum = str(metadata.get("source_checksum_sha256") or "").strip().lower()
    if requested_revision or requested_checksum:
        matches = [
            source
            for source in candidates
            if (not requested_revision or source.source_revision == requested_revision)
            and (not requested_checksum or source.checksum_sha256 == requested_checksum)
        ]
        if len(matches) != 1:
            raise HTTPException(
                status_code=422,
                detail=f"{entity_label} source binding is ambiguous or does not exactly match the controlled source tuple",
            )
        selected = matches[0]
    elif len(candidates) == 1:
        selected = candidates[0]
    else:
        raise HTTPException(
            status_code=422,
            detail=f"{entity_label} requires source_revision and source_checksum_sha256 because multiple source revisions share the reference",
        )
    metadata["source_revision"] = selected.source_revision
    metadata["source_checksum_sha256"] = selected.checksum_sha256
    metadata.setdefault("source_binding", "CONTROLLED_SOURCE_TUPLE")
    return metadata


def canonicalize_entity_source_bindings(
    payload: schemas.ContentRevisionCreate,
) -> schemas.ContentRevisionCreate:
    positions = []
    for row in payload.positions:
        positions.append(
            row.model_copy(
                update={
                    "metadata_json": _bound_metadata(
                        payload=payload,
                        source_reference=row.source_reference,
                        metadata_json=row.metadata_json,
                        entity_label=f"Position {row.code}",
                    )
                }
            )
        )
    components = []
    for row in payload.components:
        components.append(
            row.model_copy(
                update={
                    "metadata_json": _bound_metadata(
                        payload=payload,
                        source_reference=row.source_reference,
                        metadata_json=row.metadata_json,
                        entity_label=f"Component {row.definition_code}",
                    )
                }
            )
        )
    return payload.model_copy(update={"positions": positions, "components": components})


def _validate_effectivity(task: schemas.ContentTaskCreate) -> None:
    raw = (task.raw_effectivity_text or "").strip()
    expression = task.effectivity_expression_json or {}
    if raw and not expression and raw.upper() not in UNIVERSAL_EFFECTIVITY:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Task {task.task_code} has source effectivity wording but no governed "
                "machine-readable effectivity expression"
            ),
        )
    if expression:
        try:
            evaluate_expression(expression, {})
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Task {task.task_code} contains an invalid effectivity expression: {exc}",
            ) from exc


def _validate_publication_source(
    db: Session,
    *,
    source: schemas.ContentSourceCreate,
    pack: models.AircraftContentPack | None,
    for_publication: bool,
) -> None:
    if not source.publication_revision_id:
        if source.temporary_revision_id:
            raise HTTPException(
                status_code=422,
                detail=f"Source {source.reference} links a temporary revision without its base publication revision",
            )
        return
    revision = db.get(models.AircraftOemPublicationRevision, source.publication_revision_id)
    if not revision:
        raise HTTPException(
            status_code=422,
            detail=f"Source {source.reference} publication revision is unknown",
        )
    publication = revision.publication
    if pack is not None and not _pack_matches_publication(pack, publication):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Source {source.reference} belongs to {publication.manufacturer} "
                f"{publication.family} {publication.series or ''} and cannot back "
                f"content pack {pack.manufacturer} {pack.family} {pack.series or ''}"
            ),
        )
    allowed = {"VERIFIED", "CURRENT", "SUPERSEDED"}
    if revision.status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Source {source.reference} is linked to an unverified OEM publication revision",
        )
    if for_publication and revision.status != "CURRENT":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Source {source.reference} is not backed by the CURRENT OEM publication revision"
            ),
        )
    if source.temporary_revision_id:
        temporary = db.get(models.AircraftOemTemporaryRevision, source.temporary_revision_id)
        if not temporary or temporary.publication_revision_id != revision.id:
            raise HTTPException(
                status_code=422,
                detail=f"Source {source.reference} temporary revision does not belong to its base publication revision",
            )
        if temporary.status != "ACTIVE" or temporary.verified_at is None:
            raise HTTPException(
                status_code=422,
                detail=f"Source {source.reference} temporary revision is not an active verified source",
            )
        if source.source_revision != temporary.temporary_revision_code:
            raise HTTPException(
                status_code=422,
                detail=f"Source {source.reference} revision does not match its temporary revision",
            )
        if source.checksum_sha256 != temporary.checksum_sha256:
            raise HTTPException(
                status_code=422,
                detail=f"Source {source.reference} checksum does not match its temporary revision",
            )
    else:
        if source.source_revision != revision.revision_code:
            raise HTTPException(
                status_code=422,
                detail=f"Source {source.reference} revision does not match its OEM publication revision",
            )
        if source.checksum_sha256 != revision.checksum_sha256:
            raise HTTPException(
                status_code=422,
                detail=f"Source {source.reference} checksum does not match its OEM publication revision",
            )


def validate_source_backing(
    payload: schemas.ContentRevisionCreate,
    *,
    db: Session | None = None,
    pack: models.AircraftContentPack | None = None,
    for_publication: bool = False,
) -> None:
    references = {row.reference for row in payload.sources}
    if payload.positions or payload.components or payload.tasks or payload.resources:
        if not payload.sources:
            raise HTTPException(
                status_code=422,
                detail="Engineering content requires controlled sources",
            )
    if db is not None:
        for row in payload.sources:
            _validate_publication_source(
                db,
                source=row,
                pack=pack,
                for_publication=for_publication,
            )

    source_keys = {
        (row.reference, row.source_revision, row.checksum_sha256)
        for row in payload.sources
    }
    position_codes = {row.code for row in payload.positions}
    for row in payload.positions:
        if row.source_reference not in references:
            raise HTTPException(
                status_code=422,
                detail=f"Position {row.code} has no matching source",
            )
        binding = _bound_metadata(
            payload=payload,
            source_reference=row.source_reference,
            metadata_json=row.metadata_json,
            entity_label=f"Position {row.code}",
        )
        if (
            row.source_reference,
            binding["source_revision"],
            binding["source_checksum_sha256"],
        ) not in source_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Position {row.code} has no exact controlled source match",
            )
    for row in payload.components:
        if row.position_code not in position_codes:
            raise HTTPException(
                status_code=422,
                detail=f"Component {row.definition_code} references an unknown position",
            )
        binding = _bound_metadata(
            payload=payload,
            source_reference=row.source_reference,
            metadata_json=row.metadata_json,
            entity_label=f"Component {row.definition_code}",
        )
        if (
            row.source_reference,
            binding["source_revision"],
            binding["source_checksum_sha256"],
        ) not in source_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Component {row.definition_code} has no exact controlled source match",
            )
    for row in payload.tasks:
        key = (
            row.source_reference,
            row.source_revision,
            row.source_checksum_sha256,
        )
        if key not in source_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Task {row.task_code} has no exact source match",
            )
        _validate_effectivity(row)
    for row in payload.resources:
        key = (
            row.source_reference,
            row.source_revision,
            row.source_checksum_sha256,
        )
        if key not in source_keys:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Resource {row.resource_kind}:{row.resource_code} has no exact source match"
                ),
            )


def _payload_from_revision(revision: models.AircraftContentPackRevision) -> schemas.ContentRevisionCreate:
    # Use the existing source-of-truth serializer so validation/hashing stays in
    # one contract even while governance is extended.
    return _ORIGINALS["_payload_from_revision"](revision)


def create_revision(
    db: Session,
    *,
    pack: models.AircraftContentPack,
    payload: schemas.ContentRevisionCreate,
    user: account_models.User,
):
    payload = canonicalize_entity_source_bindings(payload)
    validate_source_backing(payload, db=db, pack=pack, for_publication=False)
    return _ORIGINALS["create_revision"](
        db,
        pack=pack,
        payload=payload,
        user=user,
    )


def publish_revision(
    db: Session,
    *,
    revision: models.AircraftContentPackRevision,
    expected_content_hash: str,
    user: account_models.User,
):
    payload = _payload_from_revision(revision)
    validate_source_backing(
        payload,
        db=db,
        pack=revision.pack,
        for_publication=True,
    )
    return _ORIGINALS["publish_revision"](
        db,
        revision=revision,
        expected_content_hash=expected_content_hash,
        user=user,
    )


def decide_oem_publication_revision(
    db: Session,
    *,
    revision: models.AircraftOemPublicationRevision,
    payload: schemas.OemPublicationRevisionDecision,
    user: account_models.User,
):
    require_platform_human(user)
    _ORIGINALS["_advisory_lock"](
        db,
        f"aircraft-oem-publication-decision:{revision.publication_id}",
    )
    row = (
        db.query(models.AircraftOemPublicationRevision)
        .filter(models.AircraftOemPublicationRevision.id == revision.id)
        .with_for_update(of=models.AircraftOemPublicationRevision)
        .one()
    )
    before = row.status
    now = datetime.now(timezone.utc)
    if payload.action == "VERIFY":
        if row.status != "CANDIDATE":
            raise HTTPException(
                status_code=409,
                detail="Only candidate OEM revisions can be verified",
            )
        row.status = "VERIFIED"
        row.verified_by_user_id = user.id
        row.verified_at = now
    elif payload.action == "MAKE_CURRENT":
        if row.status not in {"VERIFIED", "CURRENT"}:
            raise HTTPException(
                status_code=409,
                detail="Only verified OEM revisions can become current",
            )
        previous = (
            db.query(models.AircraftOemPublicationRevision)
            .filter(
                models.AircraftOemPublicationRevision.publication_id
                == row.publication_id,
                models.AircraftOemPublicationRevision.status == "CURRENT",
                models.AircraftOemPublicationRevision.id != row.id,
            )
            .with_for_update(of=models.AircraftOemPublicationRevision)
            .all()
        )
        if len(previous) > 1:
            raise HTTPException(
                status_code=409,
                detail="Publication contains multiple CURRENT revisions and requires data repair",
            )
        if previous:
            current = previous[0]
            if row.supersedes_revision_id != current.id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A replacement OEM revision must explicitly supersede the current revision"
                    ),
                )
            active_tr = db.query(models.AircraftOemTemporaryRevision.id).filter(
                models.AircraftOemTemporaryRevision.publication_revision_id
                == current.id,
                models.AircraftOemTemporaryRevision.status == "ACTIVE",
            ).first()
            if active_tr:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Active Temporary Revisions on the current publication must be "
                        "incorporated, superseded, replaced, or withdrawn before the base revision changes"
                    ),
                )
            current.status = "SUPERSEDED"
            db.add(current)
        row.status = "CURRENT"
        if row.verified_at is None:
            row.verified_at = now
            row.verified_by_user_id = user.id
    elif payload.action == "REJECT":
        if row.status not in {"CANDIDATE", "VERIFIED"}:
            raise HTTPException(
                status_code=409,
                detail="Only candidate or verified OEM revisions can be rejected",
            )
        row.status = "REJECTED"
    elif payload.action == "WITHDRAW":
        if row.status == "CURRENT":
            raise HTTPException(
                status_code=409,
                detail="A current OEM revision must be superseded before withdrawal",
            )
        if row.status in {"WITHDRAWN", "REJECTED"}:
            raise HTTPException(status_code=409, detail="OEM revision is already closed")
        row.status = "WITHDRAWN"

    metadata = dict(row.metadata_json or {})
    decisions = list(metadata.get("decisions") or [])
    decisions.append(
        {
            "action": payload.action,
            "note": payload.decision_note,
            "actor_user_id": user.id,
            "at": now.isoformat(),
        }
    )
    metadata["decisions"] = decisions
    row.metadata_json = metadata
    db.add(row)
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_PUBLICATION_REVISION",
        entity_id=row.id,
        action=payload.action,
        before={"status": before},
        after={"status": row.status},
        metadata={"decision_note": payload.decision_note},
        critical=True,
    )
    db.commit()
    db.refresh(row)
    return row


def create_temporary_revision(
    db: Session,
    *,
    publication_revision: models.AircraftOemPublicationRevision,
    payload: schemas.OemTemporaryRevisionCreate,
    user: account_models.User,
):
    require_source_contributor(user)
    if publication_revision.status not in {"VERIFIED", "CURRENT"}:
        raise HTTPException(
            status_code=409,
            detail="Temporary revisions require a verified or current base publication revision",
        )
    _ORIGINALS["_advisory_lock"](
        db,
        f"aircraft-oem-tr:{publication_revision.id}:{payload.temporary_revision_code}",
    )
    duplicate = db.query(models.AircraftOemTemporaryRevision.id).filter(
        models.AircraftOemTemporaryRevision.publication_revision_id
        == publication_revision.id,
        models.AircraftOemTemporaryRevision.temporary_revision_code
        == payload.temporary_revision_code,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Temporary revision already exists")
    if payload.replaces_temporary_revision_code:
        prior = db.query(models.AircraftOemTemporaryRevision).filter(
            models.AircraftOemTemporaryRevision.publication_revision_id
            == publication_revision.id,
            models.AircraftOemTemporaryRevision.temporary_revision_code
            == payload.replaces_temporary_revision_code,
        ).first()
        if not prior:
            raise HTTPException(
                status_code=422,
                detail="Replacement Temporary Revision does not exist on the base publication revision",
            )
    now = datetime.now(timezone.utc)
    platform = bool(getattr(user, "is_superuser", False))
    row = models.AircraftOemTemporaryRevision(
        publication_revision_id=publication_revision.id,
        **payload.model_dump(),
        status="ACTIVE" if platform else "CANDIDATE",
        submitted_by_user_id=user.id,
        submitted_by_amo_id=user.amo_id,
        verified_by_user_id=user.id if platform else None,
        verified_at=now if platform else None,
    )
    db.add(row)
    db.flush()
    if platform and row.replaces_temporary_revision_code:
        _replace_prior_temporary_revision(db, row=row)
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_TEMPORARY_REVISION",
        entity_id=row.id,
        action="ACTIVATE" if platform else "SUBMIT_CANDIDATE",
        after={
            "temporary_revision_code": row.temporary_revision_code,
            "status": row.status,
            "verified": row.verified_at is not None,
        },
        critical=platform,
    )
    db.commit()
    db.refresh(row)
    return row


def _replace_prior_temporary_revision(
    db: Session,
    *,
    row: models.AircraftOemTemporaryRevision,
) -> None:
    code = (row.replaces_temporary_revision_code or "").strip()
    if not code:
        return
    prior = (
        db.query(models.AircraftOemTemporaryRevision)
        .filter(
            models.AircraftOemTemporaryRevision.publication_revision_id
            == row.publication_revision_id,
            models.AircraftOemTemporaryRevision.temporary_revision_code == code,
            models.AircraftOemTemporaryRevision.id != row.id,
        )
        .with_for_update(of=models.AircraftOemTemporaryRevision)
        .first()
    )
    if not prior:
        raise HTTPException(
            status_code=422,
            detail="Replacement Temporary Revision does not exist on the base publication revision",
        )
    if prior.status != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail="Only an active Temporary Revision can be replaced",
        )
    prior.status = "REPLACED"
    db.add(prior)


def governed_temporary_revision_decision(
    db: Session,
    *,
    temporary_revision: models.AircraftOemTemporaryRevision,
    payload: backend_schemas.OemTemporaryRevisionGovernanceDecision,
    user: account_models.User,
):
    require_platform_human(user)
    _ORIGINALS["_advisory_lock"](
        db,
        f"aircraft-oem-tr-decision:{temporary_revision.id}",
    )
    row = (
        db.query(models.AircraftOemTemporaryRevision)
        .filter(models.AircraftOemTemporaryRevision.id == temporary_revision.id)
        .with_for_update(of=models.AircraftOemTemporaryRevision)
        .one()
    )
    before = row.status
    now = datetime.now(timezone.utc)
    if payload.action == "ACTIVATE":
        if row.status == "ACTIVE" and row.verified_at is not None:
            return row
        if row.status != "CANDIDATE":
            raise HTTPException(
                status_code=409,
                detail="Only candidate Temporary Revisions can be activated",
            )
        if row.publication_revision.status != "CURRENT":
            raise HTTPException(
                status_code=409,
                detail="A Temporary Revision can only be activated against the CURRENT base revision",
            )
        row.status = "ACTIVE"
        row.verified_by_user_id = user.id
        row.verified_at = now
        _replace_prior_temporary_revision(db, row=row)
    elif payload.action == "REJECT":
        if row.status != "CANDIDATE":
            raise HTTPException(
                status_code=409,
                detail="Only candidate Temporary Revisions can be rejected",
            )
        row.status = "REJECTED"
    else:
        status_map = {
            "INCORPORATE": "INCORPORATED",
            "SUPERSEDE": "SUPERSEDED",
            "WITHDRAW": "WITHDRAWN",
            "REPLACE": "REPLACED",
        }
        if row.status != "ACTIVE":
            raise HTTPException(
                status_code=409,
                detail=f"Only active Temporary Revisions can be {payload.action.lower()}d",
            )
        row.status = status_map[payload.action]

    metadata = dict(row.metadata_json or {})
    decisions = list(metadata.get("decisions") or [])
    decisions.append(
        {
            "action": payload.action,
            "note": payload.decision_note,
            "actor_user_id": user.id,
            "at": now.isoformat(),
        }
    )
    metadata["decisions"] = decisions
    row.metadata_json = metadata
    db.add(row)
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_TEMPORARY_REVISION",
        entity_id=row.id,
        action=payload.action,
        before={"status": before},
        after={"status": row.status},
        metadata={"decision_note": payload.decision_note},
        critical=True,
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
):
    action_map = {
        "ACTIVE": "ACTIVATE",
        "INCORPORATED": "INCORPORATE",
        "SUPERSEDED": "SUPERSEDE",
        "WITHDRAWN": "WITHDRAW",
        "REPLACED": "REPLACE",
    }
    governed = backend_schemas.OemTemporaryRevisionGovernanceDecision(
        action=action_map[payload.status],
        decision_note=payload.decision_note,
    )
    return governed_temporary_revision_decision(
        db,
        temporary_revision=temporary_revision,
        payload=governed,
        user=user,
    )


def _watch_metadata(
    watch: models.AircraftOemSourceWatch,
) -> tuple[int, datetime | None, datetime | None, str | None, int]:
    metadata = dict(watch.metadata_json or {})
    interval = int(metadata.get("check_interval_hours") or 168)
    last_success = None
    raw_success = metadata.get("last_success_at")
    if raw_success:
        try:
            last_success = datetime.fromisoformat(str(raw_success))
        except ValueError:
            last_success = None
    code = str(metadata.get("last_result_code") or "").upper() or None
    failures = int(metadata.get("consecutive_failures") or 0)
    next_due = (
        watch.last_checked_at + timedelta(hours=interval)
        if watch.last_checked_at is not None
        else None
    )
    return interval, next_due, last_success, code, failures


def create_source_watch(
    db: Session,
    *,
    publication: models.AircraftOemPublication,
    payload: schemas.OemSourceWatchCreate,
    user: account_models.User,
):
    require_platform_human(user)
    metadata = dict(payload.metadata_json or {})
    metadata.setdefault("check_interval_hours", 168)
    governed = payload.model_copy(update={"metadata_json": metadata})
    return _ORIGINALS["create_source_watch"](
        db,
        publication=publication,
        payload=governed,
        user=user,
    )


def create_governed_source_watch(
    db: Session,
    *,
    publication: models.AircraftOemPublication,
    payload: backend_schemas.OemSourceWatchGovernanceCreate,
    user: account_models.User,
):
    legacy = schemas.OemSourceWatchCreate(
        channel_type=payload.channel_type,
        reference=payload.reference,
        is_active=payload.is_active,
        metadata_json={
            **payload.metadata_json,
            "check_interval_hours": payload.check_interval_hours,
        },
    )
    return create_source_watch(
        db,
        publication=publication,
        payload=legacy,
        user=user,
    )


def record_governed_source_watch_check(
    db: Session,
    *,
    watch: models.AircraftOemSourceWatch,
    payload: backend_schemas.OemSourceWatchGovernanceCheck,
    user: account_models.User,
):
    require_platform_human(user)
    checked_at = payload.checked_at or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    watch.last_checked_at = checked_at
    watch.last_seen_marker = payload.seen_marker
    watch.last_result = payload.detail
    metadata = dict(watch.metadata_json or {})
    metadata["last_result_code"] = payload.result_code
    if payload.result_code in {"OK", "CHANGE_DETECTED"}:
        metadata["last_success_at"] = checked_at.isoformat()
        metadata["consecutive_failures"] = 0
    else:
        metadata["consecutive_failures"] = int(
            metadata.get("consecutive_failures") or 0
        ) + 1
    watch.metadata_json = metadata
    db.add(watch)
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_SOURCE_WATCH",
        entity_id=watch.id,
        action="CHECK",
        after={
            "result_code": payload.result_code,
            "seen_marker": payload.seen_marker,
            "checked_at": checked_at.isoformat(),
        },
        metadata={"detail": payload.detail},
        critical=payload.result_code == "CHANGE_DETECTED",
    )
    db.commit()
    db.refresh(watch)
    return watch


def record_source_watch_check(
    db: Session,
    *,
    watch: models.AircraftOemSourceWatch,
    payload: schemas.OemSourceWatchCheck,
    user: account_models.User,
):
    raw = payload.result.strip()
    code = raw.upper()
    if code not in WATCH_RESULT_CODES:
        code = "OK" if code.startswith("OK") else "ERROR"
    governed = backend_schemas.OemSourceWatchGovernanceCheck(
        result_code=code,
        seen_marker=payload.seen_marker,
        detail=raw,
    )
    return record_governed_source_watch_check(
        db,
        watch=watch,
        payload=governed,
        user=user,
    )


def governed_watch_read(
    watch: models.AircraftOemSourceWatch,
    *,
    now: datetime | None = None,
) -> backend_schemas.OemSourceWatchGovernanceRead:
    now = now or datetime.now(timezone.utc)
    interval, next_due, last_success, code, failures = _watch_metadata(watch)
    overdue = watch.is_active and (
        watch.last_checked_at is None or (next_due is not None and next_due < now)
    )
    base = schemas.OemSourceWatchRead.model_validate(watch).model_dump()
    return backend_schemas.OemSourceWatchGovernanceRead(
        **base,
        check_interval_hours=interval,
        next_check_due_at=next_due,
        last_success_at=last_success,
        last_result_code=code,
        consecutive_failures=failures,
        overdue=bool(overdue),
    )


def governed_publication_currentness(
    db: Session,
    *,
    publication: models.AircraftOemPublication,
) -> backend_schemas.OemPublicationGovernanceCurrentnessRead:
    revisions = (
        db.query(models.AircraftOemPublicationRevision)
        .filter(models.AircraftOemPublicationRevision.publication_id == publication.id)
        .order_by(models.AircraftOemPublicationRevision.created_at.desc())
        .all()
    )
    current = next((row for row in revisions if row.status == "CURRENT"), None)
    candidate = next(
        (row for row in revisions if row.status in {"CANDIDATE", "VERIFIED"}),
        None,
    )
    active_trs: list[models.AircraftOemTemporaryRevision] = []
    pending_trs: list[models.AircraftOemTemporaryRevision] = []
    if current:
        all_trs = (
            db.query(models.AircraftOemTemporaryRevision)
            .filter(
                models.AircraftOemTemporaryRevision.publication_revision_id
                == current.id
            )
            .order_by(
                models.AircraftOemTemporaryRevision.issue_date,
                models.AircraftOemTemporaryRevision.created_at,
            )
            .all()
        )
        active_trs = [row for row in all_trs if row.status == "ACTIVE"]
        pending_trs = [row for row in all_trs if row.status == "CANDIDATE"]
    watches = (
        db.query(models.AircraftOemSourceWatch)
        .filter(
            models.AircraftOemSourceWatch.publication_id == publication.id,
            models.AircraftOemSourceWatch.is_active.is_(True),
        )
        .order_by(
            models.AircraftOemSourceWatch.channel_type,
            models.AircraftOemSourceWatch.reference,
        )
        .all()
    )
    governed_watches = [governed_watch_read(row) for row in watches]

    if current is None:
        status = "NO_CURRENT_REVISION"
    elif pending_trs:
        status = "TEMPORARY_REVISION_REVIEW_REQUIRED"
    elif candidate is not None:
        status = "CANDIDATE_REVIEW_REQUIRED"
    elif any(row.last_result_code == "CHANGE_DETECTED" for row in governed_watches):
        status = "SOURCE_CHANGE_DETECTED"
    elif any(
        row.overdue
        or row.last_result_code in {"ERROR", "AUTH_REQUIRED", "UNAVAILABLE"}
        for row in governed_watches
    ):
        status = "SOURCE_CHECK_REQUIRED"
    elif active_trs:
        status = "TEMPORARY_REVISION_ACTIVE"
    else:
        status = "CURRENT"

    return backend_schemas.OemPublicationGovernanceCurrentnessRead(
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
        pending_temporary_revisions=[
            schemas.OemTemporaryRevisionRead.model_validate(row) for row in pending_trs
        ],
        watches=[schemas.OemSourceWatchRead.model_validate(row) for row in watches],
        governed_watches=governed_watches,
        currentness_status=status,
    )


def publication_currentness(
    db: Session,
    *,
    publication: models.AircraftOemPublication,
) -> schemas.OemPublicationCurrentnessRead:
    governed = governed_publication_currentness(db, publication=publication)
    collapse = {
        "TEMPORARY_REVISION_REVIEW_REQUIRED": "SOURCE_CHECK_REQUIRED",
        "SOURCE_CHANGE_DETECTED": "SOURCE_CHECK_REQUIRED",
    }
    return schemas.OemPublicationCurrentnessRead(
        publication=governed.publication,
        current_revision=governed.current_revision,
        newest_candidate=governed.newest_candidate,
        active_temporary_revisions=governed.active_temporary_revisions,
        watches=governed.watches,
        currentness_status=collapse.get(
            governed.currentness_status,
            governed.currentness_status,
        ),
    )


def withdraw_content_revision(
    db: Session,
    *,
    revision: models.AircraftContentPackRevision,
    payload: backend_schemas.ContentRevisionWithdraw,
    user: account_models.User,
):
    require_platform_human(user)
    _ORIGINALS["_advisory_lock"](
        db,
        f"aircraft-content-pack:withdraw:{revision.pack_id}",
    )
    row = (
        db.query(models.AircraftContentPackRevision)
        .filter(models.AircraftContentPackRevision.id == revision.id)
        .with_for_update(of=models.AircraftContentPackRevision)
        .one()
    )
    if row.status == "WITHDRAWN":
        return row
    if row.status not in {"DRAFT", "PUBLISHED", "SUPERSEDED"}:
        raise HTTPException(
            status_code=409,
            detail="Content revision cannot be withdrawn from its current state",
        )
    before = row.status
    row.status = "WITHDRAWN"
    if before == "PUBLISHED":
        row.pack.status = "SOURCE_INTAKE"
        db.add(row.pack)
    db.add(row)
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_CONTENT_PACK_REVISION",
        entity_id=row.id,
        action="WITHDRAW",
        before={"status": before},
        after={"status": "WITHDRAWN"},
        metadata={"decision_note": payload.decision_note},
        critical=True,
    )
    db.commit()
    db.refresh(row)
    return row


def set_publication_status(
    db: Session,
    *,
    publication: models.AircraftOemPublication,
    payload: backend_schemas.PublicationStatusDecision,
    user: account_models.User,
):
    require_platform_human(user)
    if publication.status == payload.status:
        return publication
    if payload.status == "INACTIVE":
        current_ids = [
            row.id
            for row in publication.revisions
            if row.status == "CURRENT"
        ]
        if current_ids:
            live_reference = (
                db.query(models.AircraftContentPackSource.id)
                .join(models.AircraftContentPackRevision)
                .filter(
                    models.AircraftContentPackSource.publication_revision_id.in_(current_ids),
                    models.AircraftContentPackRevision.status == "PUBLISHED",
                )
                .first()
            )
            if live_reference:
                raise HTTPException(
                    status_code=409,
                    detail="An OEM publication backing a published content baseline cannot be inactivated",
                )
    before = publication.status
    publication.status = payload.status
    db.add(publication)
    _audit(
        db,
        user=user,
        entity_type="AIRCRAFT_OEM_PUBLICATION",
        entity_id=publication.id,
        action="SET_STATUS",
        before={"status": before},
        after={"status": publication.status},
        metadata={"decision_note": payload.decision_note},
        critical=True,
    )
    db.commit()
    db.refresh(publication)
    return publication


def _hash_controlled(value: dict[str, Any]) -> str:
    return _ORIGINALS["_hash"](value)


def _diff_map(
    base: dict[str, str],
    target: dict[str, str],
) -> tuple[list[str], list[str], list[str]]:
    common = set(base) & set(target)
    return (
        sorted(set(target) - set(base)),
        sorted(set(base) - set(target)),
        sorted(key for key in common if base[key] != target[key]),
    )


def extended_revision_diff(
    base: models.AircraftContentPackRevision,
    target: models.AircraftContentPackRevision,
) -> backend_schemas.ContentRevisionExtendedDiffRead:
    if base.pack_id != target.pack_id:
        raise HTTPException(
            status_code=422,
            detail="Content revisions must belong to the same pack",
        )

    base_sources = {
        f"{row.reference}@{row.source_revision}": _hash_controlled(
            {
                "checksum": row.checksum_sha256,
                "authority": row.authority,
                "effective_date": row.effective_date,
                "publication_revision_id": row.publication_revision_id,
                "temporary_revision_id": row.temporary_revision_id,
                "source_page_ref": row.source_page_ref,
                "document_locator": row.document_locator,
                "provenance_json": row.provenance_json,
            }
        )
        for row in base.sources
    }
    target_sources = {
        f"{row.reference}@{row.source_revision}": _hash_controlled(
            {
                "checksum": row.checksum_sha256,
                "authority": row.authority,
                "effective_date": row.effective_date,
                "publication_revision_id": row.publication_revision_id,
                "temporary_revision_id": row.temporary_revision_id,
                "source_page_ref": row.source_page_ref,
                "document_locator": row.document_locator,
                "provenance_json": row.provenance_json,
            }
        )
        for row in target.sources
    }
    base_positions = {
        row.code: _hash_controlled(
            {
                "label": row.label,
                "position_kind": row.position_kind,
                "required": row.required,
                "source_reference": row.source_reference,
                "metadata_json": row.metadata_json,
            }
        )
        for row in base.positions
    }
    target_positions = {
        row.code: _hash_controlled(
            {
                "label": row.label,
                "position_kind": row.position_kind,
                "required": row.required,
                "source_reference": row.source_reference,
                "metadata_json": row.metadata_json,
            }
        )
        for row in target.positions
    }
    base_components = {
        row.definition_code: _hash_controlled(
            {
                "position_code": row.position_code,
                "description": row.description,
                "component_class": row.component_class,
                "accepted_part_numbers_json": row.accepted_part_numbers_json,
                "life_limit_json": row.life_limit_json,
                "metadata_json": row.metadata_json,
                "source_reference": row.source_reference,
            }
        )
        for row in base.components
    }
    target_components = {
        row.definition_code: _hash_controlled(
            {
                "position_code": row.position_code,
                "description": row.description,
                "component_class": row.component_class,
                "accepted_part_numbers_json": row.accepted_part_numbers_json,
                "life_limit_json": row.life_limit_json,
                "metadata_json": row.metadata_json,
                "source_reference": row.source_reference,
            }
        )
        for row in target.components
    }

    legacy = _ORIGINALS["compare_content_revisions"](base, target)
    added_sources, removed_sources, changed_sources = _diff_map(
        base_sources,
        target_sources,
    )
    added_positions, removed_positions, changed_positions = _diff_map(
        base_positions,
        target_positions,
    )
    added_components, removed_components, changed_components = _diff_map(
        base_components,
        target_components,
    )
    return backend_schemas.ContentRevisionExtendedDiffRead(
        base_revision_id=base.id,
        target_revision_id=target.id,
        added_sources=added_sources,
        removed_sources=removed_sources,
        changed_sources=changed_sources,
        added_positions=added_positions,
        removed_positions=removed_positions,
        changed_positions=changed_positions,
        added_components=added_components,
        removed_components=removed_components,
        changed_components=changed_components,
        added_tasks=legacy.added_tasks,
        removed_tasks=legacy.removed_tasks,
        changed_tasks=legacy.changed_tasks,
        unchanged_tasks=legacy.unchanged_tasks,
        added_resources=legacy.added_resources,
        removed_resources=legacy.removed_resources,
        changed_resources=legacy.changed_resources,
    )


def install(services_module: Any) -> None:
    """Install governance-compatible service replacements for legacy routes.

    The content-pack router predates the richer OEM governance layer.  Keeping
    the public route contract while replacing the mutable implementation avoids
    two competing write paths during the migration to the new backend API.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    names = {
        "_hash",
        "_advisory_lock",
        "_payload_from_revision",
        "create_revision",
        "publish_revision",
        "decide_oem_publication_revision",
        "create_temporary_revision",
        "decide_temporary_revision",
        "create_source_watch",
        "record_source_watch_check",
        "publication_currentness",
        "compare_content_revisions",
    }
    for name in names:
        _ORIGINALS[name] = getattr(services_module, name)

    services_module.require_source_contributor = require_source_contributor
    services_module.require_platform_human = require_platform_human
    services_module.validate_source_backing = validate_source_backing
    services_module.create_revision = create_revision
    services_module.publish_revision = publish_revision
    services_module.decide_oem_publication_revision = decide_oem_publication_revision
    services_module.create_temporary_revision = create_temporary_revision
    services_module.decide_temporary_revision = decide_temporary_revision
    services_module.create_source_watch = create_source_watch
    services_module.record_source_watch_check = record_source_watch_check
    services_module.publication_currentness = publication_currentness
    _INSTALLED = True
