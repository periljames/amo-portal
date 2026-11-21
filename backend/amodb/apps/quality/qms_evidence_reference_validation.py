"""Shared tenant-scoped reference validation for governed Quality evidence.

References are existing retained evidence-vault IDs. This helper does not upload,
replicate or deem evidence sufficient by itself.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


def require_evidence_records(
    db: Session, amo_id: str, references: list[str], *, required: bool = False,
) -> None:
    if required and not references:
        raise HTTPException(422, "At least one retained evidence record is required.")
    if len(references) > 30 or len(set(references)) != len(references):
        raise HTTPException(422, "Provide up to 30 distinct evidence record IDs.")
    if any(not isinstance(reference, str) or not reference.strip() for reference in references):
        raise HTTPException(422, "Every evidence reference must be a nonempty record ID.")
    if not references:
        return
    statement = text(
        "SELECT CAST(id AS text) FROM qms_evidence_files "
        "WHERE amo_id=:amo_id AND deleted_at IS NULL AND CAST(id AS text) IN :records"
    ).bindparams(bindparam("records", expanding=True))
    found = db.execute(statement, {"amo_id": amo_id, "records": references}).scalars().all()
    if set(found) != set(references):
        raise HTTPException(422, "Evidence record is unavailable, deleted or belongs to another organisation.")
