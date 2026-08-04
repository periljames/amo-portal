from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import User
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.fleet.models import Aircraft, AircraftUsage
from amodb.apps.maintenance_program.revision_models import AmpAircraftBaseline
from amodb.apps.technical_records.models import ExceptionQueueItem

from .migration_models import MigrationBatch, MigrationBatchStatus
from .rollout_models import (
    RolloutChecklistItem,
    RolloutGroup,
    RolloutWave,
    RolloutWaveAircraft,
    SpreadsheetRegister,
    SpreadsheetRetirementEvent,
)
from .rollout_schemas import (
    RolloutAircraftTransition,
    RolloutChecklistUpdate,
    RolloutDashboardRead,
    RolloutGroupCreate,
    RolloutGroupRead,
    RolloutWaveCreate,
    RolloutWaveRead,
    RolloutWaveTransition,
    SpreadsheetCreate,
    SpreadsheetRead,
    SpreadsheetTransition,
)


GLOBAL_CHECKLIST = (
    ("source_governance", "DATA", "Source ownership, freeze point and reconciliation process approved"),
    ("user_access", "PEOPLE", "User roles, access and support contacts confirmed"),
    ("training_complete", "PEOPLE", "Planning, Production, Quality and Technical Records users trained"),
    ("process_walkthrough", "PROCESS", "End-to-end planning, execution and records workflow demonstrated"),
    ("winair_exchange", "INTEGRATION", "WinAir exchange profile, authority and shadow reconciliation verified"),
    ("backup_restore", "CONTINGENCY", "Backup, restore and cutover rollback procedures verified"),
    ("support_readiness", "CONTINGENCY", "Cutover support rota and escalation path confirmed"),
)

AIRCRAFT_CHECKLIST = (
    ("aircraft_identity", "DATA", "Aircraft registration, MSN, model and operator identity verified"),
    ("migration_reconciled", "DATA", "Migration batch committed or existing portal record formally accepted"),
    ("utilisation_verified", "DATA", "Canonical FH/FC ledger reconciled and current"),
    ("amp_baseline_verified", "DATA", "Approved active AMP baseline verified"),
    ("component_configuration", "DATA", "Installed serialized component configuration verified"),
    ("deferrals_verified", "PROCESS", "Open deferred defects and limits verified"),
    ("dual_run_reconciled", "PROCESS", "Dual-run differences reviewed and closed"),
    ("cutover_authorized", "PROCESS", "Aircraft cutover authorized by Planning and Quality"),
    ("post_cutover_validation", "PROCESS", "Post-cutover counters, due list and records validated"),
)

WAVE_TRANSITIONS = {
    "PLANNED": {"READY", "HOLD", "CANCELLED"},
    "READY": {"IN_PROGRESS", "HOLD", "PLANNED", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETE", "HOLD"},
    "HOLD": {"PLANNED", "READY", "IN_PROGRESS", "CANCELLED"},
    "COMPLETE": set(),
    "CANCELLED": set(),
}

AIRCRAFT_TRANSITIONS = {
    "PLANNED": {"DUAL_RUN", "HOLD"},
    "DUAL_RUN": {"CUTOVER", "HOLD", "PLANNED"},
    "CUTOVER": {"VERIFIED", "HOLD", "DUAL_RUN"},
    "VERIFIED": {"COMPLETE", "HOLD", "CUTOVER"},
    "HOLD": {"PLANNED", "DUAL_RUN", "CUTOVER", "VERIFIED"},
    "COMPLETE": set(),
}

SPREADSHEET_TRANSITIONS = {
    "LIVE": {"DUAL_RUN"},
    "DUAL_RUN": {"LIVE", "READ_ONLY"},
    "READ_ONLY": {"DUAL_RUN", "RETIRED"},
    "RETIRED": {"READ_ONLY", "ARCHIVED"},
    "ARCHIVED": set(),
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str | None,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=after,
        ),
    )


def _get_group(db: Session, *, amo_id: str, group_id: str) -> RolloutGroup:
    row = db.query(RolloutGroup).filter(RolloutGroup.amo_id == amo_id, RolloutGroup.id == group_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rollout group not found")
    return row


def _get_wave(db: Session, *, amo_id: str, wave_id: str) -> RolloutWave:
    row = db.query(RolloutWave).filter(RolloutWave.amo_id == amo_id, RolloutWave.id == wave_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rollout wave not found")
    return row


def _get_wave_aircraft(db: Session, *, amo_id: str, row_id: str) -> RolloutWaveAircraft:
    row = db.query(RolloutWaveAircraft).filter(
        RolloutWaveAircraft.amo_id == amo_id,
        RolloutWaveAircraft.id == row_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rollout aircraft row not found")
    return row


def _get_spreadsheet(db: Session, *, amo_id: str, spreadsheet_id: str) -> SpreadsheetRegister:
    row = db.query(SpreadsheetRegister).filter(
        SpreadsheetRegister.amo_id == amo_id,
        SpreadsheetRegister.id == spreadsheet_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Spreadsheet register item not found")
    return row


def list_groups(db: Session, *, amo_id: str) -> list[RolloutGroupRead]:
    rows = db.query(RolloutGroup).filter(RolloutGroup.amo_id == amo_id).order_by(RolloutGroup.updated_at.desc()).all()
    return [RolloutGroupRead.model_validate(row) for row in rows]


def create_group(
    db: Session,
    *,
    amo_id: str,
    payload: RolloutGroupCreate,
    actor: User,
) -> RolloutGroup:
    duplicate = db.query(RolloutGroup).filter(RolloutGroup.amo_id == amo_id, RolloutGroup.name == payload.name).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Rollout group name already exists")
    row = RolloutGroup(
        amo_id=amo_id,
        name=payload.name,
        description=payload.description,
        status="DRAFT",
        selection_json=payload.selection_json,
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=actor.id, entity_type="RolloutGroup", entity_id=row.id, action="create", after={"name": row.name})
    return row


def _seed_checklists(db: Session, *, wave: RolloutWave) -> None:
    for key, category, label in GLOBAL_CHECKLIST:
        db.add(RolloutChecklistItem(
            amo_id=wave.amo_id,
            wave_id=wave.id,
            aircraft_serial_number=None,
            check_key=key,
            category=category,
            label=label,
            status="PENDING",
            evidence_json=[],
        ))
    for aircraft in wave.aircraft:
        for key, category, label in AIRCRAFT_CHECKLIST:
            db.add(RolloutChecklistItem(
                amo_id=wave.amo_id,
                wave_id=wave.id,
                aircraft_serial_number=aircraft.aircraft_serial_number,
                check_key=key,
                category=category,
                label=label,
                status="PENDING",
                evidence_json=[],
            ))


def create_wave(
    db: Session,
    *,
    group: RolloutGroup,
    payload: RolloutWaveCreate,
    actor: User,
) -> RolloutWave:
    if group.status in {"COMPLETE", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Completed or cancelled groups cannot accept new waves")
    duplicate = db.query(RolloutWave).filter(
        RolloutWave.group_id == group.id,
        (RolloutWave.sequence_no == payload.sequence_no) | (RolloutWave.name == payload.name),
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Wave name or sequence already exists in this group")
    aircraft_rows = []
    for serial_number in dict.fromkeys(payload.aircraft_serial_numbers):
        aircraft = db.query(Aircraft).filter(Aircraft.amo_id == group.amo_id, Aircraft.serial_number == serial_number).first()
        if not aircraft:
            raise HTTPException(status_code=404, detail=f"Aircraft {serial_number} not found")
        already = db.query(RolloutWaveAircraft).join(RolloutWave).filter(
            RolloutWaveAircraft.amo_id == group.amo_id,
            RolloutWaveAircraft.aircraft_serial_number == serial_number,
            RolloutWave.status.notin_(["COMPLETE", "CANCELLED"]),
        ).first()
        if already:
            raise HTTPException(status_code=409, detail=f"Aircraft {aircraft.registration} is already in an active rollout wave")
        aircraft_rows.append((aircraft.serial_number, aircraft.registration))
    wave = RolloutWave(
        amo_id=group.amo_id,
        group_id=group.id,
        name=payload.name,
        sequence_no=payload.sequence_no,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        status="PLANNED",
        readiness_json={},
        created_by_user_id=actor.id,
    )
    db.add(wave)
    db.flush()
    for serial_number, registration in aircraft_rows:
        db.add(RolloutWaveAircraft(
            amo_id=group.amo_id,
            wave_id=wave.id,
            aircraft_serial_number=serial_number,
            registration=registration,
            status="PLANNED",
            updated_by_user_id=actor.id,
        ))
    db.flush()
    db.expire(wave, ["aircraft"])
    _seed_checklists(db, wave=wave)
    group.status = "ACTIVE"
    db.add(group)
    db.flush()
    assess_wave(db, wave=wave)
    return wave


def update_checklist(
    db: Session,
    *,
    amo_id: str,
    checklist_id: str,
    payload: RolloutChecklistUpdate,
    actor: User,
) -> RolloutChecklistItem:
    row = db.query(RolloutChecklistItem).filter(
        RolloutChecklistItem.amo_id == amo_id,
        RolloutChecklistItem.id == checklist_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rollout checklist item not found")
    row.status = payload.status
    row.notes = payload.notes
    row.evidence_json = payload.evidence_json
    if payload.status in {"COMPLETE", "NOT_APPLICABLE"}:
        row.completed_by_user_id = actor.id
        row.completed_at = _utcnow()
    else:
        row.completed_by_user_id = None
        row.completed_at = None
    db.add(row)
    db.flush()
    assess_wave(db, wave=row.wave)
    return row


def _aircraft_system_evidence(db: Session, *, amo_id: str, serial_number: str) -> dict[str, Any]:
    usage = db.query(AircraftUsage).filter(
        AircraftUsage.amo_id == amo_id,
        AircraftUsage.aircraft_serial_number == serial_number,
    ).order_by(AircraftUsage.date.desc(), AircraftUsage.techlog_no.desc()).first()
    baseline = db.query(AmpAircraftBaseline).filter(
        AmpAircraftBaseline.amo_id == amo_id,
        AmpAircraftBaseline.aircraft_serial_number == serial_number,
        AmpAircraftBaseline.status == "ACTIVE",
    ).first()
    exceptions = db.query(ExceptionQueueItem).filter(
        ExceptionQueueItem.amo_id == amo_id,
        ExceptionQueueItem.object_id == serial_number,
        ExceptionQueueItem.status == "Open",
    ).count()
    return {
        "usage_id": usage.id if usage else None,
        "last_log_date": usage.date.isoformat() if usage else None,
        "total_hours": float(usage.ttaf_after or 0) if usage else None,
        "total_cycles": float(usage.tca_after or 0) if usage else None,
        "active_amp_baseline_id": baseline.id if baseline else None,
        "open_exceptions": exceptions,
    }


def assess_wave(db: Session, *, wave: RolloutWave) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not wave.aircraft:
        blockers.append("No aircraft are assigned to the rollout wave.")
    incomplete_global = [
        row for row in wave.checklist_items
        if row.aircraft_serial_number is None and row.status not in {"COMPLETE", "NOT_APPLICABLE"}
    ]
    if incomplete_global:
        blockers.append(f"{len(incomplete_global)} wave-level checklist item(s) remain incomplete.")
    aircraft_evidence: dict[str, Any] = {}
    for aircraft_row in wave.aircraft:
        serial = aircraft_row.aircraft_serial_number
        scoped = [row for row in wave.checklist_items if row.aircraft_serial_number == serial]
        incomplete = [row for row in scoped if row.status not in {"COMPLETE", "NOT_APPLICABLE"}]
        evidence = _aircraft_system_evidence(db, amo_id=wave.amo_id, serial_number=serial)
        aircraft_evidence[serial] = evidence
        if not evidence["usage_id"]:
            blockers.append(f"{aircraft_row.registration}: canonical utilization ledger is missing.")
        if not evidence["active_amp_baseline_id"]:
            blockers.append(f"{aircraft_row.registration}: active approved AMP baseline is missing.")
        if evidence["open_exceptions"]:
            blockers.append(f"{aircraft_row.registration}: {evidence['open_exceptions']} Technical Records exception(s) remain open.")
        if aircraft_row.migration_batch_id:
            migration = db.query(MigrationBatch).filter(
                MigrationBatch.amo_id == wave.amo_id,
                MigrationBatch.id == aircraft_row.migration_batch_id,
            ).first()
            if not migration or migration.status != MigrationBatchStatus.COMMITTED.value:
                blockers.append(f"{aircraft_row.registration}: linked migration batch is not committed.")
        elif aircraft_row.status in {"DUAL_RUN", "CUTOVER", "VERIFIED", "COMPLETE"}:
            warnings.append(f"{aircraft_row.registration}: no migration batch reference is recorded.")
        if incomplete and aircraft_row.status in {"CUTOVER", "VERIFIED", "COMPLETE"}:
            blockers.append(f"{aircraft_row.registration}: {len(incomplete)} aircraft checklist item(s) remain incomplete.")
        if aircraft_row.status == "HOLD":
            blockers.append(f"{aircraft_row.registration}: rollout is on hold{': ' + aircraft_row.hold_reason if aircraft_row.hold_reason else ''}.")
    status_value = "BLOCKED" if blockers else ("ATTENTION" if warnings else "READY")
    result = {
        "status": status_value,
        "blockers": blockers,
        "warnings": warnings,
        "metrics": {
            "aircraft": len(wave.aircraft),
            "checklist_items": len(wave.checklist_items),
            "checklist_complete": sum(1 for row in wave.checklist_items if row.status in {"COMPLETE", "NOT_APPLICABLE"}),
            "aircraft_status": dict(Counter(row.status for row in wave.aircraft)),
        },
        "aircraft_evidence": aircraft_evidence,
        "assessed_at": _utcnow().isoformat(),
    }
    wave.readiness_json = result
    db.add(wave)
    db.flush()
    return result


def transition_wave(
    db: Session,
    *,
    wave: RolloutWave,
    payload: RolloutWaveTransition,
    actor: User,
) -> RolloutWave:
    target = payload.status
    if target == wave.status:
        return wave
    if target not in WAVE_TRANSITIONS.get(wave.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid rollout wave transition {wave.status} -> {target}")
    readiness = assess_wave(db, wave=wave)
    if target == "READY" and readiness["status"] != "READY":
        raise HTTPException(status_code=409, detail={"message": "Wave is not ready", "readiness": readiness})
    if target == "IN_PROGRESS" and wave.status != "READY":
        raise HTTPException(status_code=409, detail="Wave must be READY before it can start")
    if target == "COMPLETE":
        incomplete = [row.registration for row in wave.aircraft if row.status != "COMPLETE"]
        if incomplete:
            raise HTTPException(status_code=409, detail={"message": "All aircraft must be complete", "aircraft": incomplete})
    previous = wave.status
    wave.status = target
    wave.decision_notes = payload.decision_notes
    if target == "READY":
        wave.approved_by_user_id = actor.id
        wave.approved_at = _utcnow()
    if target == "IN_PROGRESS":
        wave.started_at = _utcnow()
    if target == "COMPLETE":
        wave.completed_at = _utcnow()
    db.add(wave)
    db.flush()
    group = wave.group
    if target == "COMPLETE" and all(item.status == "COMPLETE" for item in group.waves):
        group.status = "COMPLETE"
        db.add(group)
    _audit(db, amo_id=wave.amo_id, actor_user_id=actor.id, entity_type="RolloutWave", entity_id=wave.id, action="transition", before={"status": previous}, after={"status": target, "notes": payload.decision_notes})
    return wave


def _checklist_status(wave: RolloutWave, serial_number: str, check_key: str) -> Optional[str]:
    for row in wave.checklist_items:
        if row.aircraft_serial_number == serial_number and row.check_key == check_key:
            return row.status
    return None


def transition_aircraft(
    db: Session,
    *,
    row: RolloutWaveAircraft,
    payload: RolloutAircraftTransition,
    actor: User,
) -> RolloutWaveAircraft:
    target = payload.status
    if target == row.status:
        return row
    if target not in AIRCRAFT_TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid rollout aircraft transition {row.status} -> {target}")
    evidence = _aircraft_system_evidence(db, amo_id=row.amo_id, serial_number=row.aircraft_serial_number)
    if target == "DUAL_RUN":
        if not evidence["usage_id"] or not evidence["active_amp_baseline_id"] or evidence["open_exceptions"]:
            raise HTTPException(status_code=409, detail={"message": "Aircraft is not ready for dual run", "evidence": evidence})
        if payload.migration_batch_id:
            migration = db.query(MigrationBatch).filter(
                MigrationBatch.amo_id == row.amo_id,
                MigrationBatch.id == payload.migration_batch_id,
                MigrationBatch.status == MigrationBatchStatus.COMMITTED.value,
            ).first()
            if not migration:
                raise HTTPException(status_code=409, detail="Migration batch is not committed")
            row.migration_batch_id = migration.id
    if target == "CUTOVER":
        incomplete = [
            item.check_key for item in row.wave.checklist_items
            if item.aircraft_serial_number == row.aircraft_serial_number
            and item.status not in {"COMPLETE", "NOT_APPLICABLE"}
            and item.check_key != "post_cutover_validation"
        ]
        if incomplete:
            raise HTTPException(status_code=409, detail={"message": "Aircraft checklist is incomplete", "items": incomplete})
    if target == "VERIFIED" and _checklist_status(row.wave, row.aircraft_serial_number, "post_cutover_validation") not in {"COMPLETE", "NOT_APPLICABLE"}:
        raise HTTPException(status_code=409, detail="Post-cutover validation checklist is not complete")
    previous = row.status
    row.status = target
    row.notes = payload.notes
    row.updated_by_user_id = actor.id
    row.hold_reason = payload.notes if target == "HOLD" else None
    if target == "DUAL_RUN":
        row.dual_run_started_at = _utcnow()
    if target == "CUTOVER":
        row.cutover_at = _utcnow()
    if target == "VERIFIED":
        row.verified_at = _utcnow()
    if target == "COMPLETE":
        row.completed_at = _utcnow()
    db.add(row)
    db.flush()
    assess_wave(db, wave=row.wave)
    _audit(db, amo_id=row.amo_id, actor_user_id=actor.id, entity_type="RolloutWaveAircraft", entity_id=row.id, action="transition", before={"status": previous}, after={"status": target, "notes": payload.notes})
    return row


def list_spreadsheets(db: Session, *, amo_id: str) -> list[SpreadsheetRead]:
    rows = db.query(SpreadsheetRegister).filter(SpreadsheetRegister.amo_id == amo_id).order_by(SpreadsheetRegister.updated_at.desc()).all()
    return [SpreadsheetRead.model_validate(row) for row in rows]


def create_spreadsheet(
    db: Session,
    *,
    amo_id: str,
    payload: SpreadsheetCreate,
    actor: User,
) -> SpreadsheetRegister:
    duplicate = db.query(SpreadsheetRegister).filter(
        SpreadsheetRegister.amo_id == amo_id,
        SpreadsheetRegister.name == payload.name,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Spreadsheet register name already exists")
    row = SpreadsheetRegister(
        amo_id=amo_id,
        name=payload.name,
        owner=payload.owner,
        location=payload.location,
        purpose=payload.purpose,
        data_domain=payload.data_domain,
        status="LIVE",
        replacement_route=payload.replacement_route,
        retirement_criteria_json=payload.retirement_criteria_json,
        retirement_evidence_json=[],
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    db.add(SpreadsheetRetirementEvent(
        amo_id=amo_id,
        spreadsheet_id=row.id,
        event_type="REGISTER",
        to_status="LIVE",
        notes="Spreadsheet added to controlled retirement register",
        evidence_json=[],
        actor_user_id=actor.id,
    ))
    return row


def transition_spreadsheet(
    db: Session,
    *,
    row: SpreadsheetRegister,
    payload: SpreadsheetTransition,
    actor: User,
) -> SpreadsheetRegister:
    target = payload.status
    if target == row.status:
        return row
    if target not in SPREADSHEET_TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid spreadsheet transition {row.status} -> {target}")
    if target in {"READ_ONLY", "RETIRED", "ARCHIVED"} and not row.replacement_route:
        raise HTTPException(status_code=409, detail="Replacement portal route is required")
    if target == "READ_ONLY" and not payload.evidence_json:
        raise HTTPException(status_code=409, detail="Dual-run reconciliation evidence is required before read-only mode")
    if target == "RETIRED":
        criteria = list(row.retirement_criteria_json or [])
        combined_evidence = list(dict.fromkeys([*(row.retirement_evidence_json or []), *payload.evidence_json]))
        active_aircraft = db.query(RolloutWaveAircraft).filter(
            RolloutWaveAircraft.amo_id == row.amo_id,
            RolloutWaveAircraft.status.in_(["DUAL_RUN", "CUTOVER", "HOLD"]),
        ).count()
        completed_waves = db.query(RolloutWave).filter(
            RolloutWave.amo_id == row.amo_id,
            RolloutWave.status == "COMPLETE",
        ).count()
        blockers = []
        if not criteria:
            blockers.append("No retirement criteria are recorded.")
        if len(combined_evidence) < len(criteria):
            blockers.append("Evidence does not cover every retirement criterion.")
        if active_aircraft:
            blockers.append(f"{active_aircraft} aircraft remain in dual-run, cutover, or hold state.")
        if not completed_waves:
            blockers.append("No rollout wave has completed.")
        if blockers:
            raise HTTPException(status_code=409, detail={"message": "Spreadsheet cannot be retired", "blockers": blockers})
    if target == "ARCHIVED" and row.status != "RETIRED":
        raise HTTPException(status_code=409, detail="Only a retired spreadsheet can be archived")
    previous = row.status
    row.status = target
    row.retirement_evidence_json = list(dict.fromkeys([*(row.retirement_evidence_json or []), *payload.evidence_json]))
    if target == "RETIRED":
        row.retired_at = _utcnow()
    if target == "ARCHIVED":
        row.archived_at = _utcnow()
    db.add(row)
    db.flush()
    db.add(SpreadsheetRetirementEvent(
        amo_id=row.amo_id,
        spreadsheet_id=row.id,
        event_type="STATUS_CHANGE",
        from_status=previous,
        to_status=target,
        notes=payload.notes,
        evidence_json=payload.evidence_json,
        actor_user_id=actor.id,
    ))
    _audit(db, amo_id=row.amo_id, actor_user_id=actor.id, entity_type="SpreadsheetRegister", entity_id=row.id, action="transition", before={"status": previous}, after={"status": target})
    return row


def dashboard(db: Session, *, amo_id: str) -> RolloutDashboardRead:
    aircraft_counts = Counter(row.status for row in db.query(RolloutWaveAircraft).filter(RolloutWaveAircraft.amo_id == amo_id).all())
    spreadsheet_counts = Counter(row.status for row in db.query(SpreadsheetRegister).filter(SpreadsheetRegister.amo_id == amo_id).all())
    return RolloutDashboardRead(
        groups=db.query(RolloutGroup).filter(RolloutGroup.amo_id == amo_id).count(),
        waves=db.query(RolloutWave).filter(RolloutWave.amo_id == amo_id).count(),
        active_waves=db.query(RolloutWave).filter(RolloutWave.amo_id == amo_id, RolloutWave.status.in_(["READY", "IN_PROGRESS", "HOLD"])).count(),
        aircraft_planned=aircraft_counts["PLANNED"],
        aircraft_dual_run=aircraft_counts["DUAL_RUN"],
        aircraft_cutover=aircraft_counts["CUTOVER"],
        aircraft_verified=aircraft_counts["VERIFIED"],
        aircraft_complete=aircraft_counts["COMPLETE"],
        aircraft_hold=aircraft_counts["HOLD"],
        spreadsheet_live=spreadsheet_counts["LIVE"],
        spreadsheet_dual_run=spreadsheet_counts["DUAL_RUN"],
        spreadsheet_read_only=spreadsheet_counts["READ_ONLY"],
        spreadsheet_retired=spreadsheet_counts["RETIRED"],
        spreadsheet_archived=spreadsheet_counts["ARCHIVED"],
    )
