from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from . import models

_AUDIT_REF_PATTERN = re.compile(r"^(?P<family>[A-Z0-9]+)/(?P<unit>[A-Z0-9]+)/(?P<year>\d{2})/(?P<seq>\d+)$")
_AUDIT_REFERENCE_COLUMNS = ("reference_family", "unit_code", "ref_year", "ref_sequence")


def _derive_reference_parts(audit_ref: str | None, *, planned_start: date | None, created_at: datetime | None) -> tuple[str, str, int, int]:
    if audit_ref:
        match = _AUDIT_REF_PATTERN.match(audit_ref.strip().upper())
        if match:
            return (
                match.group("family"),
                match.group("unit"),
                int(match.group("year")),
                int(match.group("seq")),
            )

    basis = planned_start or (created_at.date() if created_at else date.today())
    return ("QAR", "MO", basis.year % 100, 1)


def ensure_qms_audit_reference_schema(db: Session) -> bool:
    get_bind = getattr(db, "get_bind", None)
    if not callable(get_bind):
        return False

    bind = get_bind()
    inspector = inspect(bind)
    audit_columns = {column["name"] for column in inspector.get_columns("qms_audits")}
    missing_columns = [column for column in _AUDIT_REFERENCE_COLUMNS if column not in audit_columns]

    if not missing_columns and "qms_audit_reference_counters" in inspector.get_table_names():
        return False

    for column in missing_columns:
        if column in {"reference_family", "unit_code"}:
            db.execute(text(f"ALTER TABLE qms_audits ADD COLUMN {column} VARCHAR(16)"))
        else:
            db.execute(text(f"ALTER TABLE qms_audits ADD COLUMN {column} INTEGER"))

    if "qms_audit_reference_counters" not in inspector.get_table_names():
        models.QMSAuditReferenceCounter.__table__.create(bind=bind, checkfirst=True)

    legacy_rows = db.execute(
        text(
            """
            SELECT id, audit_ref, planned_start, created_at, reference_family, unit_code, ref_year, ref_sequence
            FROM qms_audits
            """
        )
    ).mappings()

    for row in legacy_rows:
        reference_family, unit_code, ref_year, ref_sequence = _derive_reference_parts(
            row.get("audit_ref"),
            planned_start=row.get("planned_start"),
            created_at=row.get("created_at"),
        )
        db.execute(
            text(
                """
                UPDATE qms_audits
                SET reference_family = COALESCE(reference_family, :reference_family),
                    unit_code = COALESCE(unit_code, :unit_code),
                    ref_year = COALESCE(ref_year, :ref_year),
                    ref_sequence = COALESCE(ref_sequence, :ref_sequence)
                WHERE id = :audit_id
                """
            ),
            {
                "audit_id": row["id"],
                "reference_family": reference_family,
                "unit_code": unit_code,
                "ref_year": ref_year,
                "ref_sequence": ref_sequence,
            },
        )

    db.commit()
    return True


def audit_reference_columns_present(db: Session) -> bool:
    columns = {column["name"] for column in inspect(db.get_bind()).get_columns("qms_audits")}
    return all(column in columns for column in _AUDIT_REFERENCE_COLUMNS)
