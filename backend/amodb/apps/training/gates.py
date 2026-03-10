from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_revision_training_gate_satisfied(db: Session, *, amo_id: str, package) -> None:
    if not bool(getattr(package, "requires_training", False)):
        return
    if str(getattr(package, "training_gate_policy", "NONE") or "NONE") == "NONE":
        return
    source_id = str(getattr(package, "package_id", ""))
    unresolved = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM training_requirements tr
            WHERE tr.amo_id = :amo_id
              AND tr.source_type = 'REVISION'
              AND tr.source_id = :source_id
              AND tr.blocking = true
            """
        ),
        {"amo_id": amo_id, "source_id": source_id},
    ).scalar() or 0
    if unresolved > 0:
        raise HTTPException(status_code=409, detail="Training gate blocked: required training not complete")


def ensure_finding_training_gate_satisfied(db: Session, *, amo_id: str, finding_id: str) -> None:
    unresolved = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM training_requirements tr
            WHERE tr.amo_id = :amo_id
              AND tr.source_type = 'FINDING'
              AND tr.source_id = :source_id
              AND tr.blocking = true
            """
        ),
        {"amo_id": amo_id, "source_id": finding_id},
    ).scalar() or 0
    if unresolved > 0:
        raise HTTPException(status_code=409, detail="Training gate blocked: finding-linked training incomplete")
