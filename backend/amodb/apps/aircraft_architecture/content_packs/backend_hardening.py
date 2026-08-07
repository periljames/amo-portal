from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from . import models, schemas


_INSTALLED = False
_ORIGINAL_VALIDATE: Any = None


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


def install(governance_module: Any, services_module: Any) -> None:
    global _INSTALLED, _ORIGINAL_VALIDATE
    if _INSTALLED:
        return
    _ORIGINAL_VALIDATE = governance_module.validate_source_backing
    governance_module.validate_source_backing = validate_source_backing
    services_module.validate_source_backing = validate_source_backing
    _INSTALLED = True
