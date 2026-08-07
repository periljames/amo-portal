from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from . import backend_models, governance, models


_INSTALLED = False
_ORIGINAL: Any = None


def materialize_intake(db, *, intake_id, payload, user):
    intake = db.get(backend_models.AircraftOemSourceIntake, intake_id)
    if not intake:
        raise HTTPException(status_code=404, detail="OEM source intake not found")
    publication = db.get(models.AircraftOemPublication, intake.publication_id)
    if not publication:
        raise HTTPException(status_code=409, detail="OEM source publication lineage no longer resolves")
    governed = governance.governed_publication_currentness(db, publication=publication)

    if intake.temporary_revision_id is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "A Temporary Revision intake cannot become a standalone OEM baseline. "
                "Assemble it with the approved base-publication intake and every active "
                "Temporary Revision using the governed baseline assembly endpoint."
            ),
        )
    if governed.active_temporary_revisions:
        raise HTTPException(
            status_code=409,
            detail=(
                "The OEM publication has active Temporary Revisions. A base-only intake "
                "cannot be materialized as the complete baseline; use governed baseline assembly."
            ),
        )
    return _ORIGINAL(db, intake_id=intake_id, payload=payload, user=user)


def install(backend_services_module: Any) -> None:
    global _INSTALLED, _ORIGINAL
    if _INSTALLED:
        return
    _ORIGINAL = backend_services_module.materialize_intake
    backend_services_module.materialize_intake = materialize_intake
    _INSTALLED = True
