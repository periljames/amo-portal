from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from . import common, models
from .roster_control_models import RosterAssignmentLineage


def _lineage_key(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:40]


def _assignment_signature(row: models.RosterAssignment) -> tuple[Any, ...]:
    """Conservative fallback for copies created before source references existed."""
    return (
        row.user_id,
        row.department_id,
        row.base_station_id,
        row.shift_template_id,
        common.enum_value(row.status),
        common.enum_value(row.source),
        row.starts_at,
        row.ends_at,
        row.planned_minutes,
        row.role_label,
        row.team_code,
        row.location_label,
        row.task_note,
    )


def ensure_assignment_lineages(db: Session, *, version: models.RosterVersion) -> dict[str, str]:
    """Assign stable event identity to every active assignment in a version.

    Amendment copies preserve ``source_reference_id``. That reference is the
    primary lineage key, so changing start/end time, base, shift or aircraft in
    a later amendment does not create a duplicate event in subscribed calendars.
    Exact assignment matching is retained only as a fallback for older records
    created before source references were consistently populated.
    """
    assignments = [row for row in version.assignments or [] if row.deleted_at is None]
    if not assignments:
        return {}

    existing_rows = db.query(RosterAssignmentLineage).filter(
        RosterAssignmentLineage.amo_id == version.amo_id,
        RosterAssignmentLineage.assignment_id.in_([item.id for item in assignments]),
    ).all()
    existing = {row.assignment_id: row for row in existing_rows}

    source_by_reference: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    source_by_signature: dict[tuple[Any, ...], list[models.RosterAssignment]] = defaultdict(list)
    source_lineages: dict[str, str] = {}
    if version.source_version_id:
        source_version = db.query(models.RosterVersion).filter(
            models.RosterVersion.amo_id == version.amo_id,
            models.RosterVersion.id == version.source_version_id,
        ).first()
        if source_version:
            source_lineages = ensure_assignment_lineages(db, version=source_version)
            for source in [row for row in source_version.assignments or [] if row.deleted_at is None]:
                if source.source_reference_id:
                    source_by_reference[str(source.source_reference_id)].append(source)
                source_by_signature[_assignment_signature(source)].append(source)

    claimed_sources: set[str] = set()
    for assignment in assignments:
        if assignment.id in existing:
            continue
        source_assignment = None
        if assignment.source_reference_id:
            for candidate in source_by_reference.get(str(assignment.source_reference_id), []):
                if candidate.id not in claimed_sources:
                    source_assignment = candidate
                    break
        if source_assignment is None:
            for candidate in source_by_signature.get(_assignment_signature(assignment), []):
                if candidate.id not in claimed_sources:
                    source_assignment = candidate
                    break
        if source_assignment:
            claimed_sources.add(source_assignment.id)
            lineage = source_lineages.get(source_assignment.id) or _lineage_key(
                f"{version.amo_id}:{source_assignment.source_reference_id or source_assignment.id}"
            )
        else:
            lineage = _lineage_key(
                f"{version.amo_id}:{assignment.source_reference_id or assignment.id}"
            )
        row = RosterAssignmentLineage(
            amo_id=version.amo_id,
            assignment_id=assignment.id,
            source_assignment_id=source_assignment.id if source_assignment else None,
            lineage_key=lineage,
        )
        db.add(row)
        existing[assignment.id] = row
    db.flush()
    return {assignment_id: row.lineage_key for assignment_id, row in existing.items()}
