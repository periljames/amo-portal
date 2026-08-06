"""Deterministic preview/apply integrity for governed Workforce selections."""
from __future__ import annotations

from hashlib import sha256

from sqlalchemy.orm import Session

from . import governance_directory, governance_schemas


def _governed_selection(selection) -> governance_schemas.GovernedPeopleSelection:
    if isinstance(selection, governance_schemas.GovernedPeopleSelection):
        return selection
    filters = getattr(selection, "filters", None)
    filter_values = filters.model_dump() if hasattr(filters, "model_dump") else dict(filters or {})
    return governance_schemas.GovernedPeopleSelection(
        mode=selection.mode,
        user_ids=list(getattr(selection, "user_ids", []) or []),
        exclude_user_ids=list(getattr(selection, "exclude_user_ids", []) or []),
        filters=governance_schemas.GovernedPeopleFilterInput(**filter_values),
    )


def resolve_with_token(
    db: Session,
    *,
    amo_id: str,
    selection,
) -> tuple[list[str], str]:
    governed = _governed_selection(selection)
    user_ids = governance_directory.resolve_selection_user_ids(
        db,
        amo_id=amo_id,
        selection=governed,
    )
    digest = sha256()
    digest.update(str(amo_id).encode("utf-8"))
    digest.update(b"\0")
    for user_id in sorted(user_ids):
        digest.update(str(user_id).encode("utf-8"))
        digest.update(b"\n")
    return user_ids, digest.hexdigest()
