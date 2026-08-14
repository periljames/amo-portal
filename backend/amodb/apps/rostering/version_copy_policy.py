from __future__ import annotations

from sqlalchemy.orm import Session

from . import models
from .aircraft_allocation import RosterAircraftAllocation
from .roster_control_models import RosterAssignmentLineage


def _database(args, kwargs) -> Session:
    return args[0] if args else kwargs["db"]


def preserve_copied_version_state(db: Session, *, version: models.RosterVersion) -> None:
    """Persist source identity and clone aircraft allocations for copied versions.

    The existing lineage policy runs immediately after the assignment copy and
    records the exact old-to-new assignment mapping. Use that durable mapping
    before users can edit time, base or shift fields so later amendments keep a
    stable calendar identity and direct aircraft allocations.
    """

    if not version.source_version_id:
        return

    targets = (
        db.query(models.RosterAssignment)
        .filter(
            models.RosterAssignment.amo_id == version.amo_id,
            models.RosterAssignment.version_id == version.id,
            models.RosterAssignment.deleted_at.is_(None),
        )
        .all()
    )
    if not targets:
        return

    target_ids = [row.id for row in targets]
    lineage_rows = (
        db.query(RosterAssignmentLineage)
        .filter(
            RosterAssignmentLineage.amo_id == version.amo_id,
            RosterAssignmentLineage.assignment_id.in_(target_ids),
            RosterAssignmentLineage.source_assignment_id.is_not(None),
        )
        .all()
    )
    target_by_source_id = {
        row.source_assignment_id: next(
            target for target in targets if target.id == row.assignment_id
        )
        for row in lineage_rows
        if row.source_assignment_id
    }
    if not target_by_source_id:
        return

    source_ids = list(target_by_source_id)
    sources = {
        row.id: row
        for row in db.query(models.RosterAssignment)
        .filter(
            models.RosterAssignment.amo_id == version.amo_id,
            models.RosterAssignment.version_id == version.source_version_id,
            models.RosterAssignment.id.in_(source_ids),
        )
        .all()
    }

    # Turn the source assignment identity into a stable cross-version reference.
    # Subsequent amendments inherit this value even after editable fields diverge.
    for source_id, target in target_by_source_id.items():
        source = sources.get(source_id)
        if source and not target.source_reference_id:
            target.source_reference_id = source.source_reference_id or source.id
            db.add(target)

    existing = {
        (
            row.roster_assignment_id,
            row.aircraft_serial_number,
            row.starts_at,
            row.ends_at,
        )
        for row in db.query(RosterAircraftAllocation)
        .filter(
            RosterAircraftAllocation.amo_id == version.amo_id,
            RosterAircraftAllocation.roster_assignment_id.in_(target_ids),
        )
        .all()
    }
    source_allocations = (
        db.query(RosterAircraftAllocation)
        .filter(
            RosterAircraftAllocation.amo_id == version.amo_id,
            RosterAircraftAllocation.roster_assignment_id.in_(source_ids),
        )
        .all()
    )
    for allocation in source_allocations:
        target = target_by_source_id.get(allocation.roster_assignment_id)
        if target is None:
            continue
        fingerprint = (
            target.id,
            allocation.aircraft_serial_number,
            allocation.starts_at,
            allocation.ends_at,
        )
        if fingerprint in existing:
            continue
        db.add(
            RosterAircraftAllocation(
                amo_id=version.amo_id,
                roster_assignment_id=target.id,
                aircraft_serial_number=allocation.aircraft_serial_number,
                starts_at=allocation.starts_at,
                ends_at=allocation.ends_at,
                allocation_type=allocation.allocation_type,
                notes=allocation.notes,
                created_by_user_id=target.created_by_user_id or allocation.created_by_user_id,
            )
        )
        existing.add(fingerprint)

    db.flush()


def install_service_policy(service_module) -> None:
    if getattr(service_module, "_rostering_version_copy_policy_installed", False):
        return

    original_create_version = service_module.create_version

    def create_version_with_preserved_state(*args, **kwargs):
        row = original_create_version(*args, **kwargs)
        db = _database(args, kwargs)
        preserve_copied_version_state(db, version=row)
        return row

    service_module.create_version = create_version_with_preserved_state
    service_module._rostering_version_copy_policy_installed = True
