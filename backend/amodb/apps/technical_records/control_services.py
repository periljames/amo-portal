from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.crs.models import CRS, CRSSignoff
from amodb.apps.fleet import models as fleet_models
from amodb.apps.work.models import WorkOrder

from . import models as record_models
from .control_models import AircraftUsageCorrection
from .control_schemas import (
    CanonicalUtilisationCreate,
    CanonicalUtilisationRead,
    ReconciliationScanResult,
    ReconciliationSummary,
    UsageCorrectionCreate,
    UsageCorrectionDecision,
)

HOURS_TOLERANCE = 0.01
CYCLES_TOLERANCE = 0.01
CORRECTABLE_FIELDS = {
    "entry_date": "date",
    "techlog_no": "techlog_no",
    "station": "station",
    "block_hours": "block_hours",
    "cycles": "cycles",
    "remarks": "remarks",
    "note": "note",
}
HOURS_CHAIN_FIELDS = (
    "ttesn_after",
    "ttsoh_after",
    "ttshsi_after",
    "pttsn_after",
    "pttso_after",
    "tscoa_after",
)
CYCLES_CHAIN_FIELDS = ("tcesn_after", "tcsoh_after")


def _usage_before(db: Session, *, amo_id: str, aircraft_serial_number: str, entry_date: date, techlog_no: str):
    return (
        db.query(fleet_models.AircraftUsage)
        .filter(
            fleet_models.AircraftUsage.amo_id == amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number == aircraft_serial_number,
            or_(
                fleet_models.AircraftUsage.date < entry_date,
                and_(
                    fleet_models.AircraftUsage.date == entry_date,
                    fleet_models.AircraftUsage.techlog_no < techlog_no,
                ),
            ),
        )
        .order_by(
            fleet_models.AircraftUsage.date.desc(),
            fleet_models.AircraftUsage.techlog_no.desc(),
        )
        .first()
    )


def _serialize_usage(row: fleet_models.AircraftUsage) -> dict[str, Any]:
    fields = (
        "id",
        "aircraft_serial_number",
        "date",
        "techlog_no",
        "station",
        "block_hours",
        "cycles",
        "ttaf_after",
        "tca_after",
        "ttesn_after",
        "tcesn_after",
        "ttsoh_after",
        "ttshsi_after",
        "tcsoh_after",
        "pttsn_after",
        "pttso_after",
        "tscoa_after",
        "hours_to_mx",
        "days_to_mx",
        "remarks",
        "note",
        "verification_status",
        "updated_at",
    )
    result: dict[str, Any] = {}
    for field in fields:
        value = getattr(row, field)
        result[field] = value.isoformat() if isinstance(value, (date, datetime)) else value
    return result


def utilisation_read(row: fleet_models.AircraftUsage) -> CanonicalUtilisationRead:
    return CanonicalUtilisationRead(
        id=row.id,
        tail_id=row.aircraft_serial_number,
        entry_date=row.date,
        techlog_no=row.techlog_no,
        station=row.station,
        block_hours=float(row.block_hours or 0),
        entry_cycles=float(row.cycles or 0),
        hours=float(row.ttaf_after or 0),
        cycles=float(row.tca_after or 0),
        source="AircraftUsage",
        conflict_flag=False,
        correction_reason=None,
        verification_status=row.verification_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_canonical_utilisation(db: Session, *, amo_id: str, aircraft_serial_number: str) -> list[CanonicalUtilisationRead]:
    rows = (
        db.query(fleet_models.AircraftUsage)
        .filter(
            fleet_models.AircraftUsage.amo_id == amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number == aircraft_serial_number,
        )
        .order_by(fleet_models.AircraftUsage.date.desc(), fleet_models.AircraftUsage.techlog_no.desc())
        .all()
    )
    return [utilisation_read(row) for row in rows]


def _baseline_offsets(first: fleet_models.AircraftUsage) -> tuple[float, float, dict[str, float | None]]:
    hours_offset = float(first.ttaf_after or 0) - float(first.block_hours or 0)
    cycles_offset = float(first.tca_after or 0) - float(first.cycles or 0)
    component_offsets: dict[str, float | None] = {}
    for field in HOURS_CHAIN_FIELDS:
        value = getattr(first, field)
        component_offsets[field] = None if value is None else float(value) - float(first.block_hours or 0)
    for field in CYCLES_CHAIN_FIELDS:
        value = getattr(first, field)
        component_offsets[field] = None if value is None else float(value) - float(first.cycles or 0)
    return hours_offset, cycles_offset, component_offsets


def recalculate_usage_chain(db: Session, *, amo_id: str, aircraft_serial_number: str) -> list[fleet_models.AircraftUsage]:
    rows = (
        db.query(fleet_models.AircraftUsage)
        .filter(
            fleet_models.AircraftUsage.amo_id == amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number == aircraft_serial_number,
        )
        .order_by(fleet_models.AircraftUsage.date.asc(), fleet_models.AircraftUsage.techlog_no.asc())
        .all()
    )
    if not rows:
        return []

    running_hours, running_cycles, component_running = _baseline_offsets(rows[0])
    for row in rows:
        running_hours += float(row.block_hours or 0)
        running_cycles += float(row.cycles or 0)
        row.ttaf_after = round(running_hours, 4)
        row.tca_after = round(running_cycles, 4)
        for field in HOURS_CHAIN_FIELDS:
            current = component_running[field]
            if current is not None:
                current += float(row.block_hours or 0)
                component_running[field] = current
                setattr(row, field, round(current, 4))
        for field in CYCLES_CHAIN_FIELDS:
            current = component_running[field]
            if current is not None:
                current += float(row.cycles or 0)
                component_running[field] = current
                setattr(row, field, round(current, 4))
        db.add(row)

    latest = rows[-1]
    aircraft = (
        db.query(fleet_models.Aircraft)
        .filter(
            fleet_models.Aircraft.amo_id == amo_id,
            fleet_models.Aircraft.serial_number == aircraft_serial_number,
        )
        .first()
    )
    if aircraft:
        aircraft.total_hours = latest.ttaf_after
        aircraft.total_cycles = latest.tca_after
        aircraft.last_log_date = latest.date
        db.add(aircraft)
    db.flush()
    return rows


def create_canonical_utilisation(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str | None,
    aircraft_serial_number: str,
    payload: CanonicalUtilisationCreate,
) -> fleet_models.AircraftUsage:
    if payload.tail_id != aircraft_serial_number:
        raise HTTPException(status_code=400, detail="tail mismatch")
    if payload.entry_date > date.today():
        raise HTTPException(status_code=400, detail="future dates are not allowed")
    aircraft = (
        db.query(fleet_models.Aircraft)
        .filter(
            fleet_models.Aircraft.amo_id == amo_id,
            fleet_models.Aircraft.serial_number == aircraft_serial_number,
        )
        .first()
    )
    if not aircraft:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    duplicate = (
        db.query(fleet_models.AircraftUsage)
        .filter(
            fleet_models.AircraftUsage.amo_id == amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number == aircraft_serial_number,
            fleet_models.AircraftUsage.date == payload.entry_date,
            fleet_models.AircraftUsage.techlog_no == payload.techlog_no,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Usage entry for this date and techlog already exists")

    previous = _usage_before(
        db,
        amo_id=amo_id,
        aircraft_serial_number=aircraft_serial_number,
        entry_date=payload.entry_date,
        techlog_no=payload.techlog_no,
    )
    previous_hours = float(previous.ttaf_after or 0) if previous else 0.0
    previous_cycles = float(previous.tca_after or 0) if previous else 0.0
    block_hours = payload.block_hours if payload.block_hours is not None else payload.hours - previous_hours
    entry_cycles = payload.entry_cycles if payload.entry_cycles is not None else payload.cycles - previous_cycles
    if block_hours < 0 or entry_cycles < 0:
        raise HTTPException(
            status_code=400,
            detail="Cumulative hours/cycles cannot be lower than the preceding accepted entry.",
        )

    row = fleet_models.AircraftUsage(
        amo_id=amo_id,
        aircraft_serial_number=aircraft_serial_number,
        date=payload.entry_date,
        techlog_no=payload.techlog_no,
        station=payload.station,
        block_hours=block_hours,
        cycles=entry_cycles,
        ttaf_after=payload.hours,
        tca_after=payload.cycles,
        remarks=payload.remarks,
        note=payload.note,
        verification_status="UNVERIFIED",
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    recalculate_usage_chain(db, amo_id=amo_id, aircraft_serial_number=aircraft_serial_number)
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AircraftUsage",
            entity_id=str(row.id),
            action="create",
            actor_user_id=actor_user_id,
            before_json=None,
            after_json=_serialize_usage(row),
        ),
    )
    return row


def request_usage_correction(
    db: Session,
    *,
    amo_id: str,
    usage_id: int,
    actor_user_id: str | None,
    payload: UsageCorrectionCreate,
) -> AircraftUsageCorrection:
    usage = (
        db.query(fleet_models.AircraftUsage)
        .filter(fleet_models.AircraftUsage.amo_id == amo_id, fleet_models.AircraftUsage.id == usage_id)
        .first()
    )
    if not usage:
        raise HTTPException(status_code=404, detail="Usage entry not found")
    if usage.updated_at != payload.expected_usage_updated_at:
        raise HTTPException(status_code=409, detail="Usage entry changed after it was loaded. Refresh and review it again.")
    existing = (
        db.query(AircraftUsageCorrection)
        .filter(
            AircraftUsageCorrection.amo_id == amo_id,
            AircraftUsageCorrection.usage_id == usage_id,
            AircraftUsageCorrection.status == "PENDING",
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="A pending correction already exists for this usage entry")

    proposed = {
        CORRECTABLE_FIELDS[field]: value.isoformat() if isinstance(value, date) else value
        for field in CORRECTABLE_FIELDS
        if (value := getattr(payload, field)) is not None
    }
    correction = AircraftUsageCorrection(
        amo_id=amo_id,
        usage_id=usage.id,
        aircraft_serial_number=usage.aircraft_serial_number,
        reason=payload.reason,
        proposed_values_json=proposed,
        status="PENDING",
        expected_usage_updated_at=payload.expected_usage_updated_at,
        requested_by_user_id=actor_user_id,
    )
    db.add(correction)
    db.flush()
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AircraftUsageCorrection",
            entity_id=str(correction.id),
            action="request",
            actor_user_id=actor_user_id,
            before_json=_serialize_usage(usage),
            after_json={"reason": payload.reason, "proposed": proposed},
        ),
    )
    return correction


def decide_usage_correction(
    db: Session,
    *,
    amo_id: str,
    correction_id: int,
    actor_user_id: str | None,
    payload: UsageCorrectionDecision,
) -> AircraftUsageCorrection:
    correction = (
        db.query(AircraftUsageCorrection)
        .filter(AircraftUsageCorrection.amo_id == amo_id, AircraftUsageCorrection.id == correction_id)
        .first()
    )
    if not correction:
        raise HTTPException(status_code=404, detail="Correction request not found")
    if correction.status != "PENDING":
        raise HTTPException(status_code=409, detail="Correction request has already been decided")
    usage = (
        db.query(fleet_models.AircraftUsage)
        .filter(fleet_models.AircraftUsage.amo_id == amo_id, fleet_models.AircraftUsage.id == correction.usage_id)
        .first()
    )
    if not usage:
        raise HTTPException(status_code=404, detail="Usage entry no longer exists")

    now = datetime.now(UTC)
    correction.reviewed_by_user_id = actor_user_id
    correction.review_notes = payload.review_notes
    correction.reviewed_at = now
    if payload.decision == "REJECT":
        correction.status = "REJECTED"
        db.add(correction)
        return correction
    if usage.updated_at != correction.expected_usage_updated_at:
        raise HTTPException(status_code=409, detail="Usage entry changed after the correction was requested")

    proposed = dict(correction.proposed_values_json or {})
    proposed_date = proposed.get("date", usage.date)
    if isinstance(proposed_date, str):
        proposed_date = date.fromisoformat(proposed_date)
    proposed_techlog = proposed.get("techlog_no", usage.techlog_no)
    conflict = (
        db.query(fleet_models.AircraftUsage)
        .filter(
            fleet_models.AircraftUsage.amo_id == amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number == usage.aircraft_serial_number,
            fleet_models.AircraftUsage.date == proposed_date,
            fleet_models.AircraftUsage.techlog_no == proposed_techlog,
            fleet_models.AircraftUsage.id != usage.id,
        )
        .first()
    )
    if conflict:
        raise HTTPException(status_code=409, detail="The corrected date and techlog duplicate another accepted entry")

    before = _serialize_usage(usage)
    for field, value in proposed.items():
        if field == "date" and isinstance(value, str):
            value = date.fromisoformat(value)
        setattr(usage, field, value)
    usage.updated_by_user_id = actor_user_id
    db.add(usage)
    db.flush()
    recalculate_usage_chain(db, amo_id=amo_id, aircraft_serial_number=usage.aircraft_serial_number)
    correction.status = "APPLIED"
    correction.applied_at = now
    db.add(correction)
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AircraftUsage",
            entity_id=str(usage.id),
            action="correct",
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={**_serialize_usage(usage), "correction_id": correction.id, "reason": correction.reason},
        ),
    )
    return correction


def _ensure_exception(
    db: Session,
    *,
    amo_id: str,
    ex_type: str,
    object_type: str,
    object_id: str,
    summary: str,
    actor_user_id: str | None,
) -> bool:
    existing = (
        db.query(record_models.ExceptionQueueItem)
        .filter(
            record_models.ExceptionQueueItem.amo_id == amo_id,
            record_models.ExceptionQueueItem.ex_type == ex_type,
            record_models.ExceptionQueueItem.object_type == object_type,
            record_models.ExceptionQueueItem.object_id == object_id,
            record_models.ExceptionQueueItem.status == "Open",
        )
        .first()
    )
    if existing:
        return False
    db.add(
        record_models.ExceptionQueueItem(
            amo_id=amo_id,
            ex_type=ex_type,
            object_type=object_type,
            object_id=object_id,
            summary=summary,
            created_by_user_id=actor_user_id,
        )
    )
    return True


def scan_reconciliation(db: Session, *, amo_id: str, actor_user_id: str | None) -> ReconciliationScanResult:
    created = 0
    existing = 0
    checks: Counter[str] = Counter()
    aircraft_rows = db.query(fleet_models.Aircraft).filter(fleet_models.Aircraft.amo_id == amo_id).all()

    for aircraft in aircraft_rows:
        latest = (
            db.query(fleet_models.AircraftUsage)
            .filter(
                fleet_models.AircraftUsage.amo_id == amo_id,
                fleet_models.AircraftUsage.aircraft_serial_number == aircraft.serial_number,
            )
            .order_by(fleet_models.AircraftUsage.date.desc(), fleet_models.AircraftUsage.techlog_no.desc())
            .first()
        )
        checks["aircraft_snapshot"] += 1
        if latest and (
            abs(float(aircraft.total_hours or 0) - float(latest.ttaf_after or 0)) > HOURS_TOLERANCE
            or abs(float(aircraft.total_cycles or 0) - float(latest.tca_after or 0)) > CYCLES_TOLERANCE
            or aircraft.last_log_date != latest.date
        ):
            was_created = _ensure_exception(
                db,
                amo_id=amo_id,
                ex_type="AircraftSnapshotMismatch",
                object_type="Aircraft",
                object_id=aircraft.serial_number,
                summary=(
                    f"Aircraft snapshot differs from canonical usage ledger: "
                    f"snapshot {aircraft.total_hours or 0} FH/{aircraft.total_cycles or 0} FC at {aircraft.last_log_date}; "
                    f"ledger {latest.ttaf_after or 0} FH/{latest.tca_after or 0} FC at {latest.date}."
                ),
                actor_user_id=actor_user_id,
            )
            created += int(was_created)
            existing += int(not was_created)

    legacy_rows: Iterable[record_models.AircraftUtilisation] = (
        db.query(record_models.AircraftUtilisation)
        .filter(record_models.AircraftUtilisation.amo_id == amo_id)
        .all()
    )
    for legacy in legacy_rows:
        checks["legacy_utilisation"] += 1
        canonical = (
            db.query(fleet_models.AircraftUsage)
            .filter(
                fleet_models.AircraftUsage.amo_id == amo_id,
                fleet_models.AircraftUsage.aircraft_serial_number == legacy.tail_id,
                fleet_models.AircraftUsage.date == legacy.entry_date,
            )
            .order_by(fleet_models.AircraftUsage.techlog_no.desc())
            .first()
        )
        mismatch = canonical is None or (
            abs(float(legacy.hours) - float(canonical.ttaf_after or 0)) > HOURS_TOLERANCE
            or abs(float(legacy.cycles) - float(canonical.tca_after or 0)) > CYCLES_TOLERANCE
        )
        if mismatch:
            was_created = _ensure_exception(
                db,
                amo_id=amo_id,
                ex_type="LegacyUtilisationMismatch",
                object_type="TechnicalAircraftUtilisation",
                object_id=str(legacy.id),
                summary=(
                    f"Legacy utilisation for {legacy.tail_id} on {legacy.entry_date} "
                    f"({legacy.hours} FH/{legacy.cycles} FC) does not match the canonical aircraft_usage ledger."
                ),
                actor_user_id=actor_user_id,
            )
            created += int(was_created)
            existing += int(not was_created)

    inspected_orders = (
        db.query(WorkOrder)
        .filter(WorkOrder.amo_id == amo_id, WorkOrder.status.in_(["INSPECTED", "CLOSED"]))
        .all()
    )
    for work_order in inspected_orders:
        checks["work_order_records"] += 1
        crs = db.query(CRS).filter(CRS.work_order_id == work_order.id).first()
        signoff = db.query(CRSSignoff).filter(CRSSignoff.crs_id == crs.id).first() if crs else None
        if crs is None or signoff is None:
            was_created = _ensure_exception(
                db,
                amo_id=amo_id,
                ex_type="WorkOrderRecordsIncomplete",
                object_type="WorkOrder",
                object_id=str(work_order.id),
                summary=f"WO {work_order.wo_number} is {work_order.status} but CRS or CRS sign-off is missing.",
                actor_user_id=actor_user_id,
            )
            created += int(was_created)
            existing += int(not was_created)

    return ReconciliationScanResult(
        generated_at=datetime.now(UTC),
        created=created,
        existing=existing,
        checked_aircraft=len(aircraft_rows),
        checks=dict(checks),
    )


def reconciliation_summary(db: Session, *, amo_id: str) -> ReconciliationSummary:
    rows = (
        db.query(record_models.ExceptionQueueItem)
        .filter(record_models.ExceptionQueueItem.amo_id == amo_id, record_models.ExceptionQueueItem.status == "Open")
        .all()
    )
    by_type = Counter(row.ex_type for row in rows)
    affected_aircraft = {
        row.object_id
        for row in rows
        if row.object_type == "Aircraft"
    }
    return ReconciliationSummary(
        generated_at=datetime.now(UTC),
        open_total=len(rows),
        by_type=dict(by_type),
        affected_aircraft=len(affected_aircraft),
    )
