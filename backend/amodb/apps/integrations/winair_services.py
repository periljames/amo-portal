from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
import hashlib
import json
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.fleet import models as fleet_models
from amodb.apps.maintenance_program import service as maintenance_program_service
from amodb.apps.maintenance_program.models import AmpAircraftProgramItem
from amodb.apps.technical_records import models as technical_record_models
from amodb.apps.technical_records import control_services
from amodb.apps.technical_records.control_models import AircraftUsageCorrection
from amodb.apps.technical_records.control_schemas import CanonicalUtilisationCreate, UsageCorrectionCreate

from . import models as integration_models
from . import services as integration_services
from .winair_models import (
    WinAirConflictStatus,
    WinAirObjectMap,
    WinAirProfileStatus,
    WinAirRecordStatus,
    WinAirRunStatus,
    WinAirRunType,
    WinAirSyncConflict,
    WinAirSyncMode,
    WinAirSyncProfile,
    WinAirSyncRecord,
    WinAirSyncRun,
)
from .winair_schemas import (
    WinAirConflictDecision,
    WinAirDashboardRead,
    WinAirExportRequest,
    WinAirInboundBatch,
    WinAirInboundRecord,
    WinAirProfileCreate,
    WinAirProfileUpdate,
    WinAirReconcileRequest,
    WinAirRunRead,
)

COUNTER_DATASETS = {"AIRCRAFT_COUNTER", "FLIGHT_LOG"}
OUTBOUND_DATASETS = {"MAINTENANCE_DUE", "INSPECTION_STATUS", "DEFERRAL"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _json_default(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Unsupported value {type(value)!r}")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def _hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


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


def _get_profile(db: Session, *, amo_id: str, profile_id: str) -> WinAirSyncProfile:
    profile = (
        db.query(WinAirSyncProfile)
        .filter(WinAirSyncProfile.amo_id == amo_id, WinAirSyncProfile.id == profile_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="WinAir sync profile not found")
    return profile


def _ensure_profile_active(profile: WinAirSyncProfile) -> None:
    if profile.status != WinAirProfileStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="WinAir sync profile is disabled")


def _authority(profile: WinAirSyncProfile, dataset: str) -> str:
    return str((profile.authority_json or {}).get(dataset, "PORTAL")).upper()


def _pick(payload: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in payload and payload[name] not in (None, ""):
            return payload[name]
    return default


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        raise ValueError("entry date is required")
    return date.fromisoformat(str(value)[:10])


def _float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc


def _serialize_usage(row: fleet_models.AircraftUsage) -> dict[str, Any]:
    return {
        "id": row.id,
        "aircraft_serial_number": row.aircraft_serial_number,
        "entry_date": row.date.isoformat(),
        "techlog_no": row.techlog_no,
        "station": row.station,
        "block_hours": float(row.block_hours or 0),
        "entry_cycles": float(row.cycles or 0),
        "total_hours": float(row.ttaf_after or 0),
        "total_cycles": float(row.tca_after or 0),
        "remarks": row.remarks,
        "note": row.note,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_deferral(row: technical_record_models.Deferral) -> dict[str, Any]:
    return {
        "id": row.id,
        "aircraft_serial_number": row.tail_id,
        "defect_ref": row.defect_ref,
        "deferral_type": row.deferral_type,
        "deferred_at": row.deferred_at.isoformat(),
        "expiry_at": row.expiry_at.isoformat(),
        "status": row.status,
        "linked_wo_id": row.linked_wo_id,
        "linked_crs_id": row.linked_crs_id,
    }


def list_profiles(db: Session, *, amo_id: str) -> list[WinAirSyncProfile]:
    return (
        db.query(WinAirSyncProfile)
        .filter(WinAirSyncProfile.amo_id == amo_id)
        .order_by(WinAirSyncProfile.updated_at.desc())
        .all()
    )


def create_profile(
    db: Session,
    *,
    amo_id: str,
    payload: WinAirProfileCreate,
    actor_user_id: str | None,
) -> WinAirSyncProfile:
    config = (
        db.query(integration_models.IntegrationConfig)
        .filter(
            integration_models.IntegrationConfig.amo_id == amo_id,
            integration_models.IntegrationConfig.id == payload.integration_config_id,
        )
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="Integration configuration not found")
    if config.integration_key.lower() not in {"winair", "winair-v7", "winair_flight_ops"}:
        raise HTTPException(
            status_code=400,
            detail="The selected integration configuration is not marked as a WinAir connection.",
        )
    duplicate = (
        db.query(WinAirSyncProfile)
        .filter(
            WinAirSyncProfile.amo_id == amo_id,
            or_(
                WinAirSyncProfile.name == payload.name,
                WinAirSyncProfile.integration_config_id == payload.integration_config_id,
            ),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="A WinAir profile already exists for this name or configuration")
    profile = WinAirSyncProfile(
        amo_id=amo_id,
        integration_config_id=payload.integration_config_id,
        name=payload.name,
        status=payload.status,
        mode=payload.mode,
        transport=payload.transport,
        direction=payload.direction,
        authority_json=payload.authority_json,
        mapping_json=payload.mapping_json,
        dataset_config_json=payload.dataset_config_json,
        last_cursor_json={},
        hours_tolerance=payload.hours_tolerance,
        cycles_tolerance=payload.cycles_tolerance,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(profile)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="WinAirSyncProfile",
        entity_id=profile.id,
        action="create",
        after={"name": profile.name, "mode": profile.mode, "direction": profile.direction},
    )
    return profile


def update_profile(
    db: Session,
    *,
    amo_id: str,
    profile_id: str,
    payload: WinAirProfileUpdate,
    actor_user_id: str | None,
) -> WinAirSyncProfile:
    profile = _get_profile(db, amo_id=amo_id, profile_id=profile_id)
    before = {
        "name": profile.name,
        "status": profile.status,
        "mode": profile.mode,
        "direction": profile.direction,
        "authority_json": profile.authority_json,
    }
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    profile.updated_by_user_id = actor_user_id
    db.add(profile)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="WinAirSyncProfile",
        entity_id=profile.id,
        action="update",
        before=before,
        after={
            "name": profile.name,
            "status": profile.status,
            "mode": profile.mode,
            "direction": profile.direction,
            "authority_json": profile.authority_json,
        },
    )
    return profile


def _new_run(
    db: Session,
    *,
    profile: WinAirSyncProfile,
    run_type: str,
    datasets: Iterable[str],
    actor_user_id: str | None,
    dry_run: bool = False,
) -> WinAirSyncRun:
    run = WinAirSyncRun(
        amo_id=profile.amo_id,
        profile_id=profile.id,
        run_type=run_type,
        status=WinAirRunStatus.RUNNING.value,
        dry_run=dry_run,
        requested_datasets_json=list(datasets),
        cursor_before_json=dict(profile.last_cursor_json or {}),
        cursor_after_json={},
        counts_json={"received": 0, "applied": 0, "staged": 0, "skipped": 0, "conflicts": 0, "failed": 0},
        started_at=_utcnow(),
        triggered_by_user_id=actor_user_id,
    )
    db.add(run)
    db.flush()
    return run


def _finish_run(
    db: Session,
    *,
    profile: WinAirSyncProfile,
    run: WinAirSyncRun,
    counts: Counter,
    cursor: Optional[dict[str, Any]] = None,
    error_summary: str | None = None,
) -> WinAirSyncRun:
    run.counts_json = {
        "received": int(counts["received"]),
        "applied": int(counts["applied"]),
        "staged": int(counts["staged"]),
        "skipped": int(counts["skipped"]),
        "conflicts": int(counts["conflicts"]),
        "failed": int(counts["failed"]),
        "exported": int(counts["exported"]),
    }
    run.cursor_after_json = cursor or {}
    run.finished_at = _utcnow()
    run.error_summary = error_summary
    if error_summary and not sum(counts.values()):
        run.status = WinAirRunStatus.FAILED.value
    elif counts["failed"] or counts["conflicts"]:
        run.status = WinAirRunStatus.PARTIAL.value
    else:
        run.status = WinAirRunStatus.COMPLETED.value
    if run.status == WinAirRunStatus.COMPLETED.value:
        profile.last_success_at = run.finished_at
        profile.last_error = None
        if cursor:
            profile.last_cursor_json = cursor
    elif error_summary:
        profile.last_error = error_summary
    db.add(profile)
    db.add(run)
    db.flush()
    return run


def _aircraft_for_record(
    db: Session,
    *,
    profile: WinAirSyncProfile,
    dataset: str,
    external_key: str,
    payload: dict[str, Any],
) -> Optional[fleet_models.Aircraft]:
    existing_map = (
        db.query(WinAirObjectMap)
        .filter(
            WinAirObjectMap.profile_id == profile.id,
            WinAirObjectMap.dataset == dataset,
            WinAirObjectMap.external_key == external_key,
            WinAirObjectMap.local_object_type == "Aircraft",
        )
        .first()
    )
    if existing_map:
        return (
            db.query(fleet_models.Aircraft)
            .filter(
                fleet_models.Aircraft.amo_id == profile.amo_id,
                fleet_models.Aircraft.serial_number == existing_map.local_object_id,
            )
            .first()
        )

    explicit_map = (profile.mapping_json or {}).get("aircraft", {})
    mapped_serial = explicit_map.get(external_key) if isinstance(explicit_map, dict) else None
    serial_number = mapped_serial or _pick(payload, "aircraft_serial_number", "tail_id", "serial_number", "msn")
    registration = _pick(payload, "registration", "aircraft_registration", "tail_number", "reg")
    query = db.query(fleet_models.Aircraft).filter(fleet_models.Aircraft.amo_id == profile.amo_id)
    conditions = []
    if serial_number:
        conditions.append(fleet_models.Aircraft.serial_number == str(serial_number))
    if registration:
        conditions.append(fleet_models.Aircraft.registration == str(registration))
    if not conditions:
        return None
    return query.filter(or_(*conditions)).first()


def _normalize_counter_record(
    db: Session,
    *,
    profile: WinAirSyncProfile,
    record: WinAirInboundRecord,
) -> tuple[dict[str, Any], Optional[fleet_models.Aircraft]]:
    payload = record.payload
    aircraft = _aircraft_for_record(
        db,
        profile=profile,
        dataset=record.dataset,
        external_key=record.external_key,
        payload=payload,
    )
    normalized = {
        "aircraft_serial_number": aircraft.serial_number if aircraft else _pick(payload, "aircraft_serial_number", "tail_id", "serial_number"),
        "registration": aircraft.registration if aircraft else _pick(payload, "registration", "aircraft_registration", "tail_number", "reg"),
        "entry_date": _parse_date(_pick(payload, "entry_date", "date", "flight_date", "log_date")).isoformat(),
        "techlog_no": str(_pick(payload, "techlog_no", "log_no", "flight_log_no", "journey_log_no", default=record.external_key)),
        "station": _pick(payload, "station", "airport", "base"),
        "total_hours": _float(_pick(payload, "total_hours", "ttaf", "current_hours", "aircraft_hours"), "total_hours"),
        "total_cycles": _float(_pick(payload, "total_cycles", "tca", "current_cycles", "aircraft_cycles"), "total_cycles"),
        "block_hours": None,
        "entry_cycles": None,
        "remarks": _pick(payload, "remarks", "notes", "comment"),
    }
    block_hours = _pick(payload, "block_hours", "flight_hours", "hours_delta")
    entry_cycles = _pick(payload, "entry_cycles", "cycles_delta", "landings")
    if block_hours is not None:
        normalized["block_hours"] = _float(block_hours, "block_hours")
    if entry_cycles is not None:
        normalized["entry_cycles"] = _float(entry_cycles, "entry_cycles")
    return normalized, aircraft


def _upsert_object_map(
    db: Session,
    *,
    profile: WinAirSyncProfile,
    dataset: str,
    external_key: str,
    local_object_type: str,
    local_object_id: str,
    source_hash: str,
    local_payload: dict[str, Any],
    canonical_key: str | None = None,
) -> WinAirObjectMap:
    row = (
        db.query(WinAirObjectMap)
        .filter(
            WinAirObjectMap.profile_id == profile.id,
            WinAirObjectMap.dataset == dataset,
            WinAirObjectMap.external_key == external_key,
        )
        .first()
    )
    if not row:
        row = WinAirObjectMap(
            amo_id=profile.amo_id,
            profile_id=profile.id,
            dataset=dataset,
            external_key=external_key,
            local_object_type=local_object_type,
            local_object_id=local_object_id,
        )
    row.canonical_key = canonical_key
    row.local_object_type = local_object_type
    row.local_object_id = local_object_id
    row.last_source_hash = source_hash
    row.last_local_hash = _hash(local_payload)
    row.last_synced_at = _utcnow()
    db.add(row)
    db.flush()
    return row


def _create_conflict(
    db: Session,
    *,
    record: WinAirSyncRecord,
    conflict_type: str,
    local_payload: dict[str, Any],
    differences: dict[str, Any],
) -> WinAirSyncConflict:
    conflict = WinAirSyncConflict(
        amo_id=record.amo_id,
        profile_id=record.profile_id,
        run_id=record.run_id,
        record_id=record.id,
        dataset=record.dataset,
        external_key=record.external_key,
        conflict_type=conflict_type,
        source_payload_json=record.normalized_payload_json,
        local_payload_json=local_payload,
        field_differences_json=differences,
        status=WinAirConflictStatus.OPEN.value,
    )
    record.status = WinAirRecordStatus.CONFLICT.value
    record.action = "CONFLICT"
    record.local_hash = _hash(local_payload) if local_payload else None
    record.error = conflict_type.replace("_", " ").title()
    db.add(record)
    db.add(conflict)
    db.flush()
    return conflict


def _counter_differences(normalized: dict[str, Any], local: dict[str, Any], profile: WinAirSyncProfile) -> dict[str, Any]:
    differences: dict[str, Any] = {}
    hours_tolerance = float(profile.hours_tolerance or 0)
    cycles_tolerance = int(profile.cycles_tolerance or 0)
    for source_key, local_key, tolerance in (
        ("total_hours", "total_hours", hours_tolerance),
        ("total_cycles", "total_cycles", cycles_tolerance),
        ("block_hours", "block_hours", hours_tolerance),
        ("entry_cycles", "entry_cycles", cycles_tolerance),
    ):
        source_value = normalized.get(source_key)
        local_value = local.get(local_key)
        if source_value is None or local_value is None:
            continue
        if abs(float(source_value) - float(local_value)) > tolerance:
            differences[source_key] = {"external": source_value, "local": local_value, "tolerance": tolerance}
    for key in ("entry_date", "techlog_no", "station"):
        if normalized.get(key) is not None and normalized.get(key) != local.get(key):
            differences[key] = {"external": normalized.get(key), "local": local.get(key)}
    return differences


def _process_counter_record(
    db: Session,
    *,
    profile: WinAirSyncProfile,
    run: WinAirSyncRun,
    inbound: WinAirInboundRecord,
    actor_user_id: str | None,
    dry_run: bool,
) -> tuple[WinAirSyncRecord, str]:
    source_hash = _hash(inbound.payload)
    try:
        normalized, aircraft = _normalize_counter_record(db, profile=profile, record=inbound)
    except Exception as exc:
        sync_record = WinAirSyncRecord(
            amo_id=profile.amo_id,
            profile_id=profile.id,
            run_id=run.id,
            dataset=inbound.dataset,
            direction="INBOUND",
            external_key=inbound.external_key,
            action="VALIDATE",
            status=WinAirRecordStatus.FAILED.value,
            source_payload_json=inbound.payload,
            normalized_payload_json={},
            source_hash=source_hash,
            error=str(exc),
        )
        db.add(sync_record)
        db.flush()
        return sync_record, "failed"

    sync_record = WinAirSyncRecord(
        amo_id=profile.amo_id,
        profile_id=profile.id,
        run_id=run.id,
        dataset=inbound.dataset,
        direction="INBOUND",
        external_key=inbound.external_key,
        action="CREATE",
        status=WinAirRecordStatus.STAGED.value,
        source_payload_json=inbound.payload,
        normalized_payload_json=normalized,
        source_hash=source_hash,
    )
    db.add(sync_record)
    db.flush()

    if _authority(profile, inbound.dataset) == "PORTAL":
        _create_conflict(
            db,
            record=sync_record,
            conflict_type="AUTHORITY_MISMATCH",
            local_payload={},
            differences={"authority": {"external": "WINAIR", "configured": "PORTAL"}},
        )
        return sync_record, "conflicts"
    if not aircraft:
        _create_conflict(
            db,
            record=sync_record,
            conflict_type="UNMAPPED_AIRCRAFT",
            local_payload={},
            differences={"aircraft": {"external": normalized.get("aircraft_serial_number") or normalized.get("registration"), "local": None}},
        )
        return sync_record, "conflicts"
    sync_record.local_object_type = "Aircraft"
    sync_record.local_object_id = aircraft.serial_number

    pending_correction = (
        db.query(AircraftUsageCorrection)
        .filter(
            AircraftUsageCorrection.amo_id == profile.amo_id,
            AircraftUsageCorrection.aircraft_serial_number == aircraft.serial_number,
            AircraftUsageCorrection.status == "PENDING",
        )
        .first()
    )
    if pending_correction:
        _create_conflict(
            db,
            record=sync_record,
            conflict_type="LOCAL_CORRECTION_PENDING",
            local_payload={"correction_id": pending_correction.id},
            differences={"correction": {"external": inbound.external_key, "local": pending_correction.id}},
        )
        return sync_record, "conflicts"

    entry_date = date.fromisoformat(normalized["entry_date"])
    duplicate = (
        db.query(fleet_models.AircraftUsage)
        .filter(
            fleet_models.AircraftUsage.amo_id == profile.amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number == aircraft.serial_number,
            fleet_models.AircraftUsage.date == entry_date,
            fleet_models.AircraftUsage.techlog_no == normalized["techlog_no"],
        )
        .first()
    )
    if duplicate:
        local_payload = _serialize_usage(duplicate)
        differences = _counter_differences(normalized, local_payload, profile)
        sync_record.local_object_type = "AircraftUsage"
        sync_record.local_object_id = str(duplicate.id)
        sync_record.local_hash = _hash(local_payload)
        if differences:
            _create_conflict(
                db,
                record=sync_record,
                conflict_type="DUPLICATE_MISMATCH",
                local_payload=local_payload,
                differences=differences,
            )
            return sync_record, "conflicts"
        sync_record.action = "SKIP"
        sync_record.status = WinAirRecordStatus.SKIPPED.value
        sync_record.applied_at = _utcnow()
        _upsert_object_map(
            db,
            profile=profile,
            dataset=inbound.dataset,
            external_key=inbound.external_key,
            local_object_type="AircraftUsage",
            local_object_id=str(duplicate.id),
            source_hash=source_hash,
            local_payload=local_payload,
            canonical_key=f"{aircraft.serial_number}:{entry_date.isoformat()}:{normalized['techlog_no']}",
        )
        return sync_record, "skipped"

    latest = (
        db.query(fleet_models.AircraftUsage)
        .filter(
            fleet_models.AircraftUsage.amo_id == profile.amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number == aircraft.serial_number,
        )
        .order_by(fleet_models.AircraftUsage.date.desc(), fleet_models.AircraftUsage.techlog_no.desc())
        .first()
    )
    if latest:
        local_payload = _serialize_usage(latest)
        regression: dict[str, Any] = {}
        if float(normalized["total_hours"]) + float(profile.hours_tolerance or 0) < float(latest.ttaf_after or 0):
            regression["total_hours"] = {"external": normalized["total_hours"], "latest_local": float(latest.ttaf_after or 0)}
        if float(normalized["total_cycles"]) + int(profile.cycles_tolerance or 0) < float(latest.tca_after or 0):
            regression["total_cycles"] = {"external": normalized["total_cycles"], "latest_local": float(latest.tca_after or 0)}
        if entry_date < latest.date:
            regression["entry_date"] = {"external": entry_date.isoformat(), "latest_local": latest.date.isoformat()}
        if regression:
            _create_conflict(
                db,
                record=sync_record,
                conflict_type="COUNTER_REGRESSION",
                local_payload=local_payload,
                differences=regression,
            )
            return sync_record, "conflicts"

    if dry_run or profile.mode == WinAirSyncMode.SHADOW.value:
        sync_record.action = "STAGE"
        sync_record.status = WinAirRecordStatus.STAGED.value
        return sync_record, "staged"

    payload = CanonicalUtilisationCreate(
        tail_id=aircraft.serial_number,
        entry_date=entry_date,
        techlog_no=normalized["techlog_no"],
        station=normalized.get("station"),
        hours=float(normalized["total_hours"]),
        cycles=float(normalized["total_cycles"]),
        block_hours=normalized.get("block_hours"),
        entry_cycles=normalized.get("entry_cycles"),
        source="WINAIR",
        remarks=normalized.get("remarks"),
        note=f"Imported from WinAir profile {profile.name}; external key {inbound.external_key}",
    )
    usage = control_services.create_canonical_utilisation(
        db,
        amo_id=profile.amo_id,
        actor_user_id=actor_user_id,
        aircraft_serial_number=aircraft.serial_number,
        payload=payload,
    )
    local_payload = _serialize_usage(usage)
    sync_record.local_object_type = "AircraftUsage"
    sync_record.local_object_id = str(usage.id)
    sync_record.local_hash = _hash(local_payload)
    sync_record.action = "CREATE"
    sync_record.status = WinAirRecordStatus.APPLIED.value
    sync_record.applied_at = _utcnow()
    _upsert_object_map(
        db,
        profile=profile,
        dataset=inbound.dataset,
        external_key=inbound.external_key,
        local_object_type="AircraftUsage",
        local_object_id=str(usage.id),
        source_hash=source_hash,
        local_payload=local_payload,
        canonical_key=f"{aircraft.serial_number}:{entry_date.isoformat()}:{normalized['techlog_no']}",
    )
    return sync_record, "applied"


def ingest_batch(
    db: Session,
    *,
    amo_id: str,
    profile_id: str,
    payload: WinAirInboundBatch,
    actor_user_id: str | None,
) -> WinAirSyncRun:
    profile = _get_profile(db, amo_id=amo_id, profile_id=profile_id)
    _ensure_profile_active(profile)
    if profile.direction == "OUTBOUND_ONLY":
        raise HTTPException(status_code=409, detail="This profile is outbound only")
    datasets = sorted({record.dataset for record in payload.records})
    run = _new_run(
        db,
        profile=profile,
        run_type=WinAirRunType.DRY_RUN.value if payload.dry_run else WinAirRunType.PULL.value,
        datasets=datasets,
        actor_user_id=actor_user_id,
        dry_run=payload.dry_run,
    )
    counts: Counter = Counter()
    try:
        for inbound in payload.records:
            counts["received"] += 1
            if inbound.dataset not in COUNTER_DATASETS:
                record = WinAirSyncRecord(
                    amo_id=amo_id,
                    profile_id=profile.id,
                    run_id=run.id,
                    dataset=inbound.dataset,
                    direction="INBOUND",
                    external_key=inbound.external_key,
                    action="VALIDATE",
                    status=WinAirRecordStatus.FAILED.value,
                    source_payload_json=inbound.payload,
                    normalized_payload_json={},
                    source_hash=_hash(inbound.payload),
                    error=f"Inbound application for {inbound.dataset} is not enabled; use outbound export or reconciliation.",
                )
                db.add(record)
                counts["failed"] += 1
                continue
            _, counter_key = _process_counter_record(
                db,
                profile=profile,
                run=run,
                inbound=inbound,
                actor_user_id=actor_user_id,
                dry_run=payload.dry_run,
            )
            counts[counter_key] += 1
        _finish_run(db, profile=profile, run=run, counts=counts, cursor=payload.cursor)
    except Exception as exc:
        _finish_run(db, profile=profile, run=run, counts=counts, error_summary=str(exc))
        raise
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="WinAirSyncRun",
        entity_id=run.id,
        action="ingest",
        after={"profile_id": profile.id, "counts": run.counts_json, "dry_run": run.dry_run},
    )
    return run


def _outbound_record(
    db: Session,
    *,
    profile: WinAirSyncProfile,
    run: WinAirSyncRun,
    dataset: str,
    external_key: str,
    payload: dict[str, Any],
    local_object_type: str,
    local_object_id: str,
) -> WinAirSyncRecord:
    source_hash = _hash(payload)
    record = WinAirSyncRecord(
        amo_id=profile.amo_id,
        profile_id=profile.id,
        run_id=run.id,
        dataset=dataset,
        direction="OUTBOUND",
        external_key=external_key,
        local_object_type=local_object_type,
        local_object_id=local_object_id,
        action="EXPORT",
        status=WinAirRecordStatus.APPLIED.value,
        source_payload_json=payload,
        normalized_payload_json=payload,
        source_hash=source_hash,
        local_hash=source_hash,
        applied_at=_utcnow(),
    )
    db.add(record)
    db.flush()
    _upsert_object_map(
        db,
        profile=profile,
        dataset=dataset,
        external_key=external_key,
        local_object_type=local_object_type,
        local_object_id=local_object_id,
        source_hash=source_hash,
        local_payload=payload,
        canonical_key=external_key,
    )
    return record


def export_snapshot(
    db: Session,
    *,
    amo_id: str,
    profile_id: str,
    payload: WinAirExportRequest,
    actor_user_id: str | None,
) -> WinAirSyncRun:
    profile = _get_profile(db, amo_id=amo_id, profile_id=profile_id)
    _ensure_profile_active(profile)
    if profile.direction == "INBOUND_ONLY":
        raise HTTPException(status_code=409, detail="This profile is inbound only")
    invalid = set(payload.datasets) - OUTBOUND_DATASETS
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported outbound datasets: {sorted(invalid)}")
    run = _new_run(
        db,
        profile=profile,
        run_type=WinAirRunType.PUSH.value,
        datasets=payload.datasets,
        actor_user_id=actor_user_id,
    )
    counts: Counter = Counter()
    aircraft_filter = set(payload.aircraft_serial_numbers)
    envelope: dict[str, Any] = {
        "schema": "amo-portal.winair.flight-ops.v1",
        "generated_at": _utcnow().isoformat(),
        "profile_id": profile.id,
        "datasets": {},
    }
    try:
        overview = maintenance_program_service.get_fleet_planning_overview(
            db,
            amo_id=amo_id,
            horizon_days=payload.horizon_days,
            limit=5000,
        )
        due_rows = [
            row.model_dump(mode="json")
            for row in overview.due_items
            if not aircraft_filter or row.aircraft_serial_number in aircraft_filter
        ]
        for dataset in payload.datasets:
            if _authority(profile, dataset) == "WINAIR":
                raise HTTPException(status_code=409, detail=f"{dataset} is configured as WinAir-authoritative and cannot be exported from the portal")
            rows: list[dict[str, Any]] = []
            if dataset == "MAINTENANCE_DUE":
                rows = due_rows
                for row in rows:
                    key = f"{row['aircraft_serial_number']}:{row['program_item_id']}"
                    _outbound_record(
                        db,
                        profile=profile,
                        run=run,
                        dataset=dataset,
                        external_key=key,
                        payload=row,
                        local_object_type="AmpAircraftProgramItem",
                        local_object_id=str(row["api_id"]),
                    )
                    counts["exported"] += 1
            elif dataset == "INSPECTION_STATUS":
                rows = [
                    {
                        "aircraft_serial_number": row["aircraft_serial_number"],
                        "registration": row["registration"],
                        "program_item_id": row["program_item_id"],
                        "task_code": row.get("task_code"),
                        "task_title": row["task_title"],
                        "status": row["status"],
                        "next_due_date": row.get("next_due_date"),
                        "next_due_hours": row.get("next_due_hours"),
                        "next_due_cycles": row.get("next_due_cycles"),
                    }
                    for row in due_rows
                ]
                for row in rows:
                    key = f"{row['aircraft_serial_number']}:{row['program_item_id']}"
                    _outbound_record(
                        db,
                        profile=profile,
                        run=run,
                        dataset=dataset,
                        external_key=key,
                        payload=row,
                        local_object_type="AmpAircraftProgramItem",
                        local_object_id=str(row["program_item_id"]),
                    )
                    counts["exported"] += 1
            elif dataset == "DEFERRAL":
                query = db.query(technical_record_models.Deferral).filter(
                    technical_record_models.Deferral.amo_id == amo_id,
                    technical_record_models.Deferral.status == "Open",
                )
                if aircraft_filter:
                    query = query.filter(technical_record_models.Deferral.tail_id.in_(aircraft_filter))
                rows = [_serialize_deferral(row) for row in query.order_by(technical_record_models.Deferral.expiry_at.asc()).all()]
                for row in rows:
                    key = f"{row['aircraft_serial_number']}:{row['defect_ref']}"
                    _outbound_record(
                        db,
                        profile=profile,
                        run=run,
                        dataset=dataset,
                        external_key=key,
                        payload=row,
                        local_object_type="Deferral",
                        local_object_id=str(row["id"]),
                    )
                    counts["exported"] += 1
            envelope["datasets"][dataset] = rows

        integration_services.enqueue_outbound_event(
            db,
            amo_id=amo_id,
            integration_id=profile.integration_config_id,
            event_type="winair.tech_dispatch_snapshot",
            payload_json=envelope,
            idempotency_key=f"winair:{profile.id}:{run.id}:tech-dispatch",
            created_by_user_id=actor_user_id,
        )
        _finish_run(db, profile=profile, run=run, counts=counts)
    except Exception as exc:
        _finish_run(db, profile=profile, run=run, counts=counts, error_summary=str(exc))
        raise
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="WinAirSyncRun",
        entity_id=run.id,
        action="export",
        after={"datasets": payload.datasets, "counts": run.counts_json},
    )
    return run


def _local_payload_for_map(db: Session, mapping: WinAirObjectMap) -> Optional[dict[str, Any]]:
    if mapping.local_object_type == "AircraftUsage":
        row = db.get(fleet_models.AircraftUsage, int(mapping.local_object_id))
        return _serialize_usage(row) if row else None
    if mapping.local_object_type == "Deferral":
        row = db.get(technical_record_models.Deferral, int(mapping.local_object_id))
        return _serialize_deferral(row) if row else None
    if mapping.local_object_type == "AmpAircraftProgramItem":
        row = db.get(AmpAircraftProgramItem, int(mapping.local_object_id))
        if not row:
            return None
        return {
            "id": row.id,
            "aircraft_serial_number": row.aircraft_serial_number,
            "program_item_id": row.program_item_id,
            "status": row.status.value if hasattr(row.status, "value") else str(row.status),
            "next_due_date": row.next_due_date.isoformat() if row.next_due_date else None,
            "next_due_hours": float(row.next_due_hours) if row.next_due_hours is not None else None,
            "next_due_cycles": float(row.next_due_cycles) if row.next_due_cycles is not None else None,
        }
    if mapping.local_object_type == "Aircraft":
        row = db.query(fleet_models.Aircraft).filter(fleet_models.Aircraft.serial_number == mapping.local_object_id).first()
        if not row:
            return None
        return {
            "aircraft_serial_number": row.serial_number,
            "registration": row.registration,
            "total_hours": float(row.total_hours or 0),
            "total_cycles": float(row.total_cycles or 0),
            "last_log_date": row.last_log_date.isoformat() if row.last_log_date else None,
        }
    return None


def reconcile(
    db: Session,
    *,
    amo_id: str,
    profile_id: str,
    payload: WinAirReconcileRequest,
    actor_user_id: str | None,
) -> WinAirSyncRun:
    profile = _get_profile(db, amo_id=amo_id, profile_id=profile_id)
    _ensure_profile_active(profile)
    run = _new_run(
        db,
        profile=profile,
        run_type=WinAirRunType.RECONCILE.value,
        datasets=payload.datasets,
        actor_user_id=actor_user_id,
    )
    counts: Counter = Counter()
    mappings = (
        db.query(WinAirObjectMap)
        .filter(
            WinAirObjectMap.amo_id == amo_id,
            WinAirObjectMap.profile_id == profile.id,
            WinAirObjectMap.dataset.in_(payload.datasets),
        )
        .all()
    )
    for mapping in mappings:
        counts["received"] += 1
        latest_source_record = (
            db.query(WinAirSyncRecord)
            .filter(
                WinAirSyncRecord.profile_id == profile.id,
                WinAirSyncRecord.dataset == mapping.dataset,
                WinAirSyncRecord.external_key == mapping.external_key,
            )
            .order_by(WinAirSyncRecord.created_at.desc())
            .first()
        )
        source_payload = latest_source_record.normalized_payload_json if latest_source_record else {}
        local_payload = _local_payload_for_map(db, mapping)
        record = WinAirSyncRecord(
            amo_id=amo_id,
            profile_id=profile.id,
            run_id=run.id,
            dataset=mapping.dataset,
            direction="INTERNAL",
            external_key=mapping.external_key,
            local_object_type=mapping.local_object_type,
            local_object_id=mapping.local_object_id,
            action="RECONCILE",
            status=WinAirRecordStatus.SKIPPED.value,
            source_payload_json=source_payload,
            normalized_payload_json=source_payload,
            source_hash=mapping.last_source_hash or _hash(source_payload),
            local_hash=_hash(local_payload) if local_payload else None,
        )
        db.add(record)
        db.flush()
        if local_payload is None:
            _create_conflict(
                db,
                record=record,
                conflict_type="LOCAL_OBJECT_MISSING",
                local_payload={},
                differences={"local_object": {"expected": mapping.local_object_id, "actual": None}},
            )
            counts["conflicts"] += 1
            continue
        current_hash = _hash(local_payload)
        if mapping.last_local_hash and current_hash != mapping.last_local_hash:
            _create_conflict(
                db,
                record=record,
                conflict_type="LOCAL_CHANGED_SINCE_SYNC",
                local_payload=local_payload,
                differences={"hash": {"at_last_sync": mapping.last_local_hash, "current": current_hash}},
            )
            counts["conflicts"] += 1
            continue
        record.applied_at = _utcnow()
        counts["skipped"] += 1
    _finish_run(db, profile=profile, run=run, counts=counts)
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="WinAirSyncRun",
        entity_id=run.id,
        action="reconcile",
        after={"counts": run.counts_json},
    )
    return run


def list_runs(
    db: Session,
    *,
    amo_id: str,
    profile_id: str | None = None,
    limit: int = 100,
) -> list[WinAirSyncRun]:
    query = db.query(WinAirSyncRun).filter(WinAirSyncRun.amo_id == amo_id)
    if profile_id:
        query = query.filter(WinAirSyncRun.profile_id == profile_id)
    return query.order_by(WinAirSyncRun.started_at.desc()).limit(max(1, min(limit, 500))).all()


def list_records(
    db: Session,
    *,
    amo_id: str,
    run_id: str,
) -> list[WinAirSyncRecord]:
    run = db.query(WinAirSyncRun).filter(WinAirSyncRun.amo_id == amo_id, WinAirSyncRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="WinAir sync run not found")
    return (
        db.query(WinAirSyncRecord)
        .filter(WinAirSyncRecord.amo_id == amo_id, WinAirSyncRecord.run_id == run_id)
        .order_by(WinAirSyncRecord.created_at.asc())
        .all()
    )


def list_conflicts(
    db: Session,
    *,
    amo_id: str,
    profile_id: str | None = None,
    status_filter: str | None = "OPEN",
) -> list[WinAirSyncConflict]:
    query = db.query(WinAirSyncConflict).filter(WinAirSyncConflict.amo_id == amo_id)
    if profile_id:
        query = query.filter(WinAirSyncConflict.profile_id == profile_id)
    if status_filter:
        query = query.filter(WinAirSyncConflict.status == status_filter.upper())
    return query.order_by(WinAirSyncConflict.created_at.desc()).all()


def decide_conflict(
    db: Session,
    *,
    amo_id: str,
    conflict_id: str,
    payload: WinAirConflictDecision,
    actor_user_id: str | None,
) -> WinAirSyncConflict:
    conflict = (
        db.query(WinAirSyncConflict)
        .filter(WinAirSyncConflict.amo_id == amo_id, WinAirSyncConflict.id == conflict_id)
        .first()
    )
    if not conflict:
        raise HTTPException(status_code=404, detail="WinAir conflict not found")
    if conflict.status != WinAirConflictStatus.OPEN.value:
        raise HTTPException(status_code=409, detail="WinAir conflict is already resolved")
    record = db.get(WinAirSyncRecord, conflict.record_id)
    profile = _get_profile(db, amo_id=amo_id, profile_id=conflict.profile_id)
    before = {"status": conflict.status}

    if payload.decision in {"KEEP_LOCAL", "IGNORED"}:
        conflict.status = payload.decision
        if record:
            record.status = WinAirRecordStatus.SKIPPED.value
            record.action = payload.decision
            record.applied_at = _utcnow()
            db.add(record)
    elif conflict.dataset in COUNTER_DATASETS:
        normalized = payload.merged_payload if payload.decision == "MERGED" else conflict.source_payload_json
        if not normalized:
            raise HTTPException(status_code=400, detail="No external payload is available for this resolution")
        aircraft = _aircraft_for_record(
            db,
            profile=profile,
            dataset=conflict.dataset,
            external_key=conflict.external_key,
            payload=normalized,
        )
        if not aircraft:
            raise HTTPException(status_code=409, detail="Aircraft mapping is still unresolved")
        local_usage = None
        if record and record.local_object_type == "AircraftUsage" and record.local_object_id:
            local_usage = db.get(fleet_models.AircraftUsage, int(record.local_object_id))
        if local_usage:
            proposed: dict[str, Any] = {}
            if normalized.get("entry_date"):
                proposed["entry_date"] = date.fromisoformat(str(normalized["entry_date"])[:10])
            for key in ("techlog_no", "station", "block_hours", "remarks"):
                if key in normalized and normalized[key] is not None:
                    proposed[key] = normalized[key]
            if normalized.get("entry_cycles") is not None:
                proposed["cycles"] = normalized["entry_cycles"]
            correction_payload = UsageCorrectionCreate(
                reason=f"WinAir conflict {conflict.id}: {payload.resolution_notes}",
                expected_usage_updated_at=local_usage.updated_at,
                **proposed,
            )
            correction = control_services.request_usage_correction(
                db,
                amo_id=amo_id,
                usage_id=local_usage.id,
                actor_user_id=actor_user_id,
                payload=correction_payload,
            )
            if record:
                record.status = WinAirRecordStatus.STAGED.value
                record.action = "CORRECTION_REQUESTED"
                record.error = f"Technical Records correction {correction.id} requires approval"
                db.add(record)
        else:
            create_payload = CanonicalUtilisationCreate(
                tail_id=aircraft.serial_number,
                entry_date=date.fromisoformat(str(normalized["entry_date"])[:10]),
                techlog_no=str(normalized["techlog_no"]),
                station=normalized.get("station"),
                hours=float(normalized["total_hours"]),
                cycles=float(normalized["total_cycles"]),
                block_hours=normalized.get("block_hours"),
                entry_cycles=normalized.get("entry_cycles"),
                source="WINAIR",
                remarks=normalized.get("remarks"),
                note=f"Applied from WinAir conflict {conflict.id}",
            )
            usage = control_services.create_canonical_utilisation(
                db,
                amo_id=amo_id,
                actor_user_id=actor_user_id,
                aircraft_serial_number=aircraft.serial_number,
                payload=create_payload,
            )
            local_payload = _serialize_usage(usage)
            if record:
                record.local_object_type = "AircraftUsage"
                record.local_object_id = str(usage.id)
                record.local_hash = _hash(local_payload)
                record.status = WinAirRecordStatus.APPLIED.value
                record.action = payload.decision
                record.applied_at = _utcnow()
                db.add(record)
            _upsert_object_map(
                db,
                profile=profile,
                dataset=conflict.dataset,
                external_key=conflict.external_key,
                local_object_type="AircraftUsage",
                local_object_id=str(usage.id),
                source_hash=_hash(normalized),
                local_payload=local_payload,
            )
        conflict.status = payload.decision
    else:
        conflict.status = payload.decision
        if record:
            record.status = WinAirRecordStatus.SKIPPED.value
            record.action = payload.decision
            record.error = "Resolution recorded; this dataset is portal-authoritative."
            db.add(record)

    conflict.resolution_notes = payload.resolution_notes
    conflict.resolved_by_user_id = actor_user_id
    conflict.resolved_at = _utcnow()
    db.add(conflict)
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="WinAirSyncConflict",
        entity_id=conflict.id,
        action="resolve",
        before=before,
        after={"status": conflict.status, "record_id": conflict.record_id},
    )
    return conflict


def dashboard(db: Session, *, amo_id: str) -> WinAirDashboardRead:
    profiles = db.query(WinAirSyncProfile).filter(WinAirSyncProfile.amo_id == amo_id).all()
    latest_run = (
        db.query(WinAirSyncRun)
        .filter(WinAirSyncRun.amo_id == amo_id)
        .order_by(WinAirSyncRun.started_at.desc())
        .first()
    )
    dataset_counts = Counter(
        dataset
        for (dataset,) in db.query(WinAirSyncRecord.dataset)
        .filter(WinAirSyncRecord.amo_id == amo_id)
        .all()
    )
    pending_outbox = (
        db.query(integration_models.IntegrationOutboundEvent)
        .join(
            WinAirSyncProfile,
            WinAirSyncProfile.integration_config_id == integration_models.IntegrationOutboundEvent.integration_id,
        )
        .filter(
            integration_models.IntegrationOutboundEvent.amo_id == amo_id,
            integration_models.IntegrationOutboundEvent.status == integration_models.IntegrationOutboundStatus.PENDING,
        )
        .count()
    )
    return WinAirDashboardRead(
        profiles=len(profiles),
        active_profiles=sum(1 for profile in profiles if profile.status == WinAirProfileStatus.ACTIVE.value),
        shadow_profiles=sum(1 for profile in profiles if profile.mode == WinAirSyncMode.SHADOW.value),
        open_conflicts=db.query(WinAirSyncConflict).filter(
            WinAirSyncConflict.amo_id == amo_id,
            WinAirSyncConflict.status == WinAirConflictStatus.OPEN.value,
        ).count(),
        failed_records=db.query(WinAirSyncRecord).filter(
            WinAirSyncRecord.amo_id == amo_id,
            WinAirSyncRecord.status == WinAirRecordStatus.FAILED.value,
        ).count(),
        pending_outbox=pending_outbox,
        latest_run=WinAirRunRead.model_validate(latest_run) if latest_run else None,
        dataset_counts=dict(dataset_counts),
    )
