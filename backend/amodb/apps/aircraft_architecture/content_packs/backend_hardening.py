from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import HTTPException

from . import models, schemas


_INSTALLED = False
_ORIGINAL_VALIDATE: Any = None
_GOVERNANCE: Any = None


def _series_pack_source_controls(
    payload: schemas.ContentRevisionCreate,
    *,
    pack: models.AircraftContentPack | None,
    for_publication: bool,
) -> None:
    if pack is None or not (pack.series or "").strip():
        return
    oem_sources = [
        source
        for source in payload.sources
        if source.source_type.strip().upper().startswith("OEM")
    ]
    unbound = [source.reference for source in oem_sources if not source.publication_revision_id]
    if unbound:
        raise HTTPException(
            status_code=422,
            detail=(
                "Series-specific OEM content requires first-class publication-revision "
                "lineage for every OEM source; unbound sources: " + ", ".join(sorted(unbound))
            ),
        )
    if for_publication and not any(
        source.publication_revision_id for source in payload.sources
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "A series-specific OEM baseline cannot publish without a governed OEM "
                "publication revision"
            ),
        )


def _publication_currentness_controls(payload: schemas.ContentRevisionCreate, *, db) -> None:
    by_revision: dict[str, list[schemas.ContentSourceCreate]] = defaultdict(list)
    for source in payload.sources:
        if source.publication_revision_id:
            by_revision[source.publication_revision_id].append(source)

    for revision_id, bound_sources in by_revision.items():
        revision = db.get(models.AircraftOemPublicationRevision, revision_id)
        if not revision:
            raise HTTPException(
                status_code=422,
                detail="Controlled OEM publication lineage no longer resolves",
            )
        governed = _GOVERNANCE.governed_publication_currentness(
            db,
            publication=revision.publication,
        )
        if governed.current_revision is None or governed.current_revision.id != revision.id:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"OEM source {revision.publication.publication_code} is no longer the "
                    "CURRENT publication revision"
                ),
            )
        if governed.currentness_status not in {"CURRENT", "TEMPORARY_REVISION_ACTIVE"}:
            raise HTTPException(
                status_code=409,
                detail=(
                    "OEM source currentness must be resolved before baseline publication: "
                    + governed.currentness_status
                ),
            )

        active_tr_ids = {row.id for row in governed.active_temporary_revisions}
        represented_tr_ids = {
            source.temporary_revision_id
            for source in bound_sources
            if source.temporary_revision_id
        }
        missing = active_tr_ids - represented_tr_ids
        if missing:
            missing_codes = sorted(
                row.temporary_revision_code
                for row in governed.active_temporary_revisions
                if row.id in missing
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    "Published OEM baseline must incorporate every active Temporary Revision; "
                    "missing: " + ", ".join(missing_codes)
                ),
            )


def validate_source_backing(
    payload: schemas.ContentRevisionCreate,
    *,
    db=None,
    pack: models.AircraftContentPack | None = None,
    for_publication: bool = False,
) -> None:
    _series_pack_source_controls(
        payload,
        pack=pack,
        for_publication=for_publication,
    )
    _ORIGINAL_VALIDATE(
        payload,
        db=db,
        pack=pack,
        for_publication=for_publication,
    )
    if for_publication and db is not None:
        _publication_currentness_controls(payload, db=db)


def install(governance_module: Any, services_module: Any) -> None:
    global _INSTALLED, _ORIGINAL_VALIDATE, _GOVERNANCE
    if _INSTALLED:
        return
    _ORIGINAL_VALIDATE = governance_module.validate_source_backing
    _GOVERNANCE = governance_module
    governance_module.validate_source_backing = validate_source_backing
    services_module.validate_source_backing = validate_source_backing
    _INSTALLED = True
