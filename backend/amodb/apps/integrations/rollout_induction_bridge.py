from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import synonym

from amodb.apps.aircraft_induction.models import AircraftInduction, AircraftTemplateBinding

from . import rollout_models


# Phase 7 originally persisted a migration-batch reference. Rename the mapped
# database column before mapper configuration and expose only induction_id.
_rollout_column = rollout_models.RolloutWaveAircraft.__table__.c.migration_batch_id
_rollout_column.name = "induction_id"
rollout_models.RolloutWaveAircraft.induction_id = synonym("migration_batch_id")

from . import rollout_services as base  # noqa: E402


base.AIRCRAFT_CHECKLIST = tuple(
    (
        "induction_verified" if key == "migration_reconciled" else key,
        category,
        "Universal aircraft induction, applicability snapshot and activation binding verified"
        if key == "migration_reconciled"
        else label,
    )
    for key, category, label in base.AIRCRAFT_CHECKLIST
)


def _induction_evidence(db, *, amo_id: str, serial_number: str, induction_id: str | None) -> dict[str, Any]:
    binding = db.query(AircraftTemplateBinding).filter(
        AircraftTemplateBinding.amo_id == amo_id,
        AircraftTemplateBinding.aircraft_serial_number == serial_number,
        AircraftTemplateBinding.status == "ACTIVE",
    ).first()
    induction = None
    if induction_id:
        induction = db.query(AircraftInduction).filter(
            AircraftInduction.amo_id == amo_id,
            AircraftInduction.id == induction_id,
            AircraftInduction.serial_number == serial_number,
        ).first()
    return {
        "induction_id": induction.id if induction else None,
        "induction_status": induction.status if induction else None,
        "binding_id": binding.id if binding else None,
        "binding_induction_id": binding.applicability_snapshot_id if binding else None,
        "template_revision_id": binding.template_revision_id if binding else None,
        "program_revision_id": binding.program_revision_id if binding else None,
    }


def assess_wave(db, *, wave):
    blockers: list[str] = []
    warnings: list[str] = []
    if not wave.aircraft:
        blockers.append("No aircraft are assigned to the rollout wave.")
    incomplete_global = [row for row in wave.checklist_items if row.aircraft_serial_number is None and row.status not in {"COMPLETE", "NOT_APPLICABLE"}]
    if incomplete_global:
        blockers.append(f"{len(incomplete_global)} wave-level checklist item(s) remain incomplete.")

    aircraft_evidence: dict[str, Any] = {}
    for aircraft_row in wave.aircraft:
        serial = aircraft_row.aircraft_serial_number
        scoped = [row for row in wave.checklist_items if row.aircraft_serial_number == serial]
        incomplete = [row for row in scoped if row.status not in {"COMPLETE", "NOT_APPLICABLE"}]
        system = base._aircraft_system_evidence(db, amo_id=wave.amo_id, serial_number=serial)
        induction = _induction_evidence(db, amo_id=wave.amo_id, serial_number=serial, induction_id=aircraft_row.induction_id)
        evidence = {**system, **induction}
        aircraft_evidence[serial] = evidence
        if not system["usage_id"]:
            blockers.append(f"{aircraft_row.registration}: canonical utilization ledger is missing.")
        if not system["active_amp_baseline_id"]:
            blockers.append(f"{aircraft_row.registration}: active approved AMP baseline is missing.")
        if system["open_exceptions"]:
            blockers.append(f"{aircraft_row.registration}: {system['open_exceptions']} Technical Records exception(s) remain open.")
        if not induction["binding_id"]:
            blockers.append(f"{aircraft_row.registration}: active universal aircraft binding is missing.")
        if aircraft_row.induction_id:
            if induction["induction_status"] != "ACTIVE":
                blockers.append(f"{aircraft_row.registration}: linked induction is not active.")
        elif aircraft_row.status in {"DUAL_RUN", "CUTOVER", "VERIFIED", "COMPLETE"}:
            blockers.append(f"{aircraft_row.registration}: rollout status requires an active induction reference.")
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
        "assessed_at": base._utcnow().isoformat(),
    }
    wave.readiness_json = result
    db.add(wave)
    db.flush()
    return result


def transition_aircraft(db, *, row, payload, actor):
    target = payload.status
    if target == row.status:
        return row
    if target not in base.AIRCRAFT_TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid rollout aircraft transition {row.status} -> {target}")
    evidence = base._aircraft_system_evidence(db, amo_id=row.amo_id, serial_number=row.aircraft_serial_number)
    if target == "DUAL_RUN":
        if not evidence["usage_id"] or not evidence["active_amp_baseline_id"] or evidence["open_exceptions"]:
            raise HTTPException(status_code=409, detail={"message": "Aircraft is not ready for dual run", "evidence": evidence})
        if not payload.induction_id:
            raise HTTPException(status_code=409, detail="An active universal aircraft induction is required for dual run")
        induction = db.query(AircraftInduction).filter(
            AircraftInduction.amo_id == row.amo_id,
            AircraftInduction.id == payload.induction_id,
            AircraftInduction.serial_number == row.aircraft_serial_number,
            AircraftInduction.status == "ACTIVE",
        ).first()
        binding = db.query(AircraftTemplateBinding).filter(
            AircraftTemplateBinding.amo_id == row.amo_id,
            AircraftTemplateBinding.aircraft_serial_number == row.aircraft_serial_number,
            AircraftTemplateBinding.status == "ACTIVE",
        ).first()
        if not induction or not binding:
            raise HTTPException(status_code=409, detail="Induction or active aircraft baseline binding is unavailable")
        row.induction_id = induction.id
    if target == "CUTOVER":
        incomplete = [
            item.check_key for item in row.wave.checklist_items
            if item.aircraft_serial_number == row.aircraft_serial_number
            and item.status not in {"COMPLETE", "NOT_APPLICABLE"}
            and item.check_key != "post_cutover_validation"
        ]
        if incomplete:
            raise HTTPException(status_code=409, detail={"message": "Aircraft checklist is incomplete", "items": incomplete})
    if target == "VERIFIED" and base._checklist_status(row.wave, row.aircraft_serial_number, "post_cutover_validation") not in {"COMPLETE", "NOT_APPLICABLE"}:
        raise HTTPException(status_code=409, detail="Post-cutover validation checklist is not complete")

    previous = row.status
    row.status = target
    row.notes = payload.notes
    row.updated_by_user_id = actor.id
    row.hold_reason = payload.notes if target == "HOLD" else None
    if target == "DUAL_RUN":
        row.dual_run_started_at = base._utcnow()
    if target == "CUTOVER":
        row.cutover_at = base._utcnow()
    if target == "VERIFIED":
        row.verified_at = base._utcnow()
    if target == "COMPLETE":
        row.completed_at = base._utcnow()
    db.add(row)
    db.flush()
    assess_wave(db, wave=row.wave)
    base._audit(
        db,
        amo_id=row.amo_id,
        actor_user_id=actor.id,
        entity_type="RolloutWaveAircraft",
        entity_id=row.id,
        action="transition",
        before={"status": previous},
        after={"status": target, "notes": payload.notes, "induction_id": row.induction_id},
    )
    return row


base.assess_wave = assess_wave
base.transition_aircraft = transition_aircraft
