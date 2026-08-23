from __future__ import annotations

"""Bound database work performed by large roster-generation batches.

The legacy bulk assignment implementation reloaded every assignment in the
version after each batch only to serialize the rows just created. Locked roster
lookups also triggered the model's default ``selectin`` loaders before callers
actually needed the assignment/finding graph.

This policy keeps validation, source-owned-state, idempotency and audit
behaviour intact while making those reads deliberate: locked lookups defer the
large collections until a workflow really accesses them, bulk responses load
only the assignments created by that command, and receipt replays are strictly
scoped to the target tenant/version.
"""

from typing import Any

from sqlalchemy.orm import lazyload, selectinload

from . import assignments as assignment_module
from . import common, models, schemas

_INSTALLED = False


def _load_assignments_by_id(
    db,
    *,
    amo_id: str,
    version_id: str,
    assignment_ids: list[str],
) -> dict[str, models.RosterAssignment]:
    if not assignment_ids:
        return {}
    rows = (
        db.query(models.RosterAssignment)
        .options(
            selectinload(models.RosterAssignment.user),
            selectinload(models.RosterAssignment.department),
            selectinload(models.RosterAssignment.base_station),
            selectinload(models.RosterAssignment.shift_template),
            selectinload(models.RosterAssignment.task_links),
        )
        .filter(
            models.RosterAssignment.amo_id == amo_id,
            models.RosterAssignment.version_id == version_id,
            models.RosterAssignment.id.in_(assignment_ids),
        )
        .all()
    )
    return {str(row.id): row for row in rows}


def _result_from_receipt(
    db,
    *,
    amo_id: str,
    version_id: str,
    receipt,
) -> schemas.RosterBulkAssignmentResult:
    response = receipt.response_json or {}
    receipt_version_id = str(response.get("version_id") or "")
    if receipt_version_id != str(version_id):
        raise ValueError("Idempotency key was already used for a different roster version")

    assignment_ids = [str(value) for value in response.get("assignment_ids", [])]
    by_id = _load_assignments_by_id(
        db,
        amo_id=amo_id,
        version_id=version_id,
        assignment_ids=assignment_ids,
    )
    return schemas.RosterBulkAssignmentResult(
        version_id=version_id,
        created=[common.serialize_assignment(by_id[row_id]) for row_id in assignment_ids if row_id in by_id],
        skipped=list(response.get("skipped", [])),
        conflicts=list(response.get("conflicts", [])),
        idempotent_replay=True,
    )


def _bounded_bulk_create_assignments(
    db,
    *,
    version: models.RosterVersion,
    actor_user_id: str,
    payload: schemas.RosterBulkAssignmentRequest,
) -> schemas.RosterBulkAssignmentResult:
    """Canonical bulk mutation with bounded result loading.

    This mirrors ``assignments.bulk_create_assignments`` except that both a
    normal completion and an idempotent replay load only the assignment ids
    belonging to the command instead of the entire roster version. The receipt
    check precedes revision validation so a response-lost retry of an already
    committed command can replay safely instead of failing as stale.
    """

    common.ensure_draft(version)
    request_payload = common.dump(payload)
    request_hash = common.canonical_hash(request_payload)
    receipt = common.command_receipt(
        db,
        amo_id=version.amo_id,
        idempotency_key=payload.idempotency_key,
        operation="BULK_ASSIGNMENTS",
        request_hash=request_hash,
    )
    if receipt:
        return _result_from_receipt(
            db,
            amo_id=version.amo_id,
            version_id=version.id,
            receipt=receipt,
        )
    common.check_version_revision(version, payload.expected_version_revision)

    created: list[models.RosterAssignment] = []
    skipped: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    with db.begin_nested():
        for index, item in enumerate(payload.assignments):
            try:
                create_payload = schemas.RosterAssignmentCreate(
                    **item.model_dump(exclude={"client_id"})
                )
                existing = None
                if create_payload.source_reference_id:
                    existing = (
                        db.query(models.RosterAssignment)
                        .filter(
                            models.RosterAssignment.version_id == version.id,
                            models.RosterAssignment.source == create_payload.source,
                            models.RosterAssignment.source_reference_id == create_payload.source_reference_id,
                            models.RosterAssignment.deleted_at.is_(None),
                        )
                        .first()
                    )
                if existing:
                    skipped.append(
                        {
                            "index": index,
                            "client_id": item.client_id,
                            "reason": "DUPLICATE_SOURCE_REFERENCE",
                            "assignment_id": existing.id,
                        }
                    )
                    continue
                row = assignment_module._create_assignment_row(
                    db,
                    version=version,
                    actor_user_id=actor_user_id,
                    payload=create_payload,
                    bump_parent=False,
                )
                created.append(row)
            except Exception as exc:
                conflict = {
                    "index": index,
                    "client_id": item.client_id,
                    "reason": str(exc),
                }
                conflicts.append(conflict)
                if payload.atomic:
                    raise ValueError(
                        f"Bulk assignment failed at item {index}: {exc}"
                    ) from exc
        if created:
            common.bump_version(version)
            db.add(version)
        db.flush()

    assignment_ids = [str(row.id) for row in created]
    response_json = {
        "version_id": version.id,
        "assignment_ids": assignment_ids,
        "skipped": skipped,
        "conflicts": conflicts,
    }
    common.save_command_receipt(
        db,
        amo_id=version.amo_id,
        idempotency_key=payload.idempotency_key,
        operation="BULK_ASSIGNMENTS",
        actor_user_id=actor_user_id,
        request_hash=request_hash,
        response_json=response_json,
    )
    common.audit(
        db,
        amo_id=version.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterVersion",
        entity_id=version.id,
        action="bulk_assign",
        after={
            "created_count": len(created),
            "skipped_count": len(skipped),
            "conflict_count": len(conflicts),
            "idempotency_key": payload.idempotency_key,
        },
    )
    by_id = _load_assignments_by_id(
        db,
        amo_id=version.amo_id,
        version_id=version.id,
        assignment_ids=assignment_ids,
    )
    return schemas.RosterBulkAssignmentResult(
        version_id=version.id,
        created=[common.serialize_assignment(by_id[row_id]) for row_id in assignment_ids if row_id in by_id],
        skipped=skipped,
        conflicts=conflicts,
    )


def install(service_module) -> None:
    """Install bounded mutation reads without changing public API contracts."""

    global _INSTALLED
    if _INSTALLED:
        return

    original_get_version = service_module.get_version
    original_generate_from_patterns = service_module.generate_from_patterns

    def get_version(db, *, amo_id: str, version_id: str, lock: bool = False):
        if not lock:
            return original_get_version(
                db,
                amo_id=amo_id,
                version_id=version_id,
                lock=False,
            )
        # RosterVersion collections use lazy="selectin" at the model level, so
        # merely omitting eager options still materializes them. Explicit
        # lazyload keeps the lock query bounded while preserving correctness:
        # lifecycle/validation code that genuinely needs a collection can load
        # it later through the same session. The period remains immediately
        # available because generation and validation both require it.
        return (
            db.query(models.RosterVersion)
            .options(
                selectinload(models.RosterVersion.period),
                lazyload(models.RosterVersion.source_version),
                lazyload(models.RosterVersion.assignments),
                lazyload(models.RosterVersion.validation_findings),
                lazyload(models.RosterVersion.exceptions),
            )
            .filter(
                models.RosterVersion.amo_id == amo_id,
                models.RosterVersion.id == version_id,
            )
            .with_for_update(of=models.RosterVersion)
            .first()
        )

    def generate_from_patterns(db, *, version, actor_user_id: str, payload):
        # The historical generator checks the version revision before looking
        # for its idempotency receipt. A committed request whose HTTP response
        # was lost can therefore look stale on retry. Resolve a matching receipt
        # first and return only that command's assignment ids. Receipt replay is
        # also checked against the current version so an idempotency key can
        # never replay assignments from another roster version.
        request_hash = common.canonical_hash(common.dump(payload))
        receipt = common.command_receipt(
            db,
            amo_id=version.amo_id,
            idempotency_key=payload.idempotency_key,
            operation="GENERATE_PATTERN",
            request_hash=request_hash,
        )
        if receipt:
            return _result_from_receipt(
                db,
                amo_id=version.amo_id,
                version_id=version.id,
                receipt=receipt,
            )
        return original_generate_from_patterns(
            db,
            version=version,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    service_module.get_version = get_version
    service_module._bulk_create_assignments = _bounded_bulk_create_assignments
    service_module.generate_from_patterns = generate_from_patterns
    _INSTALLED = True


__all__ = ["install"]
