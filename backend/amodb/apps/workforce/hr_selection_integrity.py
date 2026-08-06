"""Deterministic preview/apply integrity for Workforce batch selections."""
from __future__ import annotations

from hashlib import sha256

from sqlalchemy.orm import Session

from . import hr_people_directory, hr_schemas


def resolve_with_token(
    db: Session,
    *,
    amo_id: str,
    selection: hr_schemas.HrPeopleSelection,
) -> tuple[list[str], str]:
    user_ids = hr_people_directory.resolve_selection_user_ids(
        db,
        amo_id=amo_id,
        selection=selection,
    )
    digest = sha256()
    digest.update(str(amo_id).encode("utf-8"))
    digest.update(b"\0")
    for user_id in sorted(user_ids):
        digest.update(str(user_id).encode("utf-8"))
        digest.update(b"\n")
    return user_ids, digest.hexdigest()
