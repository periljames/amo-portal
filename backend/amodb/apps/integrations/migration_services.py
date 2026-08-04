from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from typing import Any, Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import User
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.fleet import models as fleet_models
from amodb.apps.maintenance_program.revision_models import AmpAircraftBaseline, AmpProgramRevision
from amodb.apps.maintenance_program import revision_services
from amodb.apps.technical_records import control_services
from amodb.apps.technical_records import models as record_models
from amodb.apps.technical_records.control_schemas import CanonicalUtilisationCreate

from .migration_models import (
    MigrationBatch,
    MigrationBatchStatus,
    MigrationCheckpoint,
    MigrationCheckpointStatus,
    MigrationReconciliationItem,
    MigrationReconciliationStatus,
    MigrationRow,
    MigrationRowStatus,
)
from .migration_schemas import (
    MigrationApprovalRequest,
    MigrationBatchCreate,
    MigrationBatchRead,
    MigrationCheckpointUpdate,
    MigrationCommitRequest,
    MigrationPresetCreate,
    MigrationReconciliationDecision,
    MigrationRollbackRequest,
    MigrationStageRequest,
    MigrationSummaryRead,
)

SUPPORTED_DATASETS = {
    "AIRCRAFT_MASTER",
    "UTILISATION",
    "COMPONENT",
    "AMP_BASELINE",
    "DEFERRAL",
    "MAINTENANCE_RECORD",
}

PILOT_SCOPE = {
    "registration": "5Y-SLS",
    "datasets": sorted(SUPPORTED_DATASETS),
    "purpose": "First controlled aircraft migration and reconciliation pilot",
}

PILOT_CHECKPOINTS = (
    ("source_frozen", "Source spreadsheets and WinAir extracts frozen and checksummed"),
    ("backup_complete", "Database backup and restore point verified"),
    ("aircraft_identity_confirmed", "5Y-SLS registration, MSN, model and operator identity confirmed"),
    ("utilisation_reconciled", "Opening FH/FC and every staged utilization row reconciled"),
    ("amp_baseline_confirmed", "Approved AMP revision and aircraft baseline confirmed"),
    ("components_reconciled", "Installed serialized component positions reconciled"),
    ("deferrals_reconciled", "Open deferred defects and expiry limits reconciled"),
    ("records_sample_verified", "Maintenance record sample and traceability verified"),
    ("rollback_tested", "Rollback procedure dry-run reviewed"),
    ("quality_approval", "Quality approval recorded for pilot cutover"),
)


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


def _get_batch(db: Session, *, amo_id: str, batch_id: str) -> MigrationBatch:
    batch = (
        db.query(MigrationBatch)
        .filter(MigrationBatch.amo_id == amo_id, MigrationBatch.id == batch_id)
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Migration batch not found")
    return batch


def _target_aircraft(db: Session, batch: MigrationBatch) -> Optional[fleet_models.Aircraft]:
    query = db.query(fleet_models.Aircraft).filter(fleet_models.Aircraft.amo_id == batch.amo_id)
    conditions = []
    if batch.target_aircraft_serial_number:
        conditions.append(fleet_models.Aircraft.serial_number == batch.target_aircraft_serial_number)
    if batch.target_registration:
        conditions.append(fleet_models.Aircraft.registration == batch.target_registration)
    return query.filter(or_(*conditions)).first() if conditions else None


def _date(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        raise ValueError(f"{field} is required")
    return date.fromisoformat(str(value)[:10])


def _datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if not value:
        raise ValueError(f"{field} is required")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc


def _pick(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if payload.get(key) not in (None, ""):
            return payload[key]
    return default


def _serialize_aircraft(row: fleet_models.Aircraft) -> dict[str, Any]:
    return {
        "serial_number": row.serial_number,
        "registration": row.registration,
        "template": row.template,
        "make": row.make,
        "model": row.model,
        "home_base": row.home_base,
        "status": row.status,
        "total_hours": float(row.total_hours or 0),
        "total_cycles": float(row.total_cycles or 0),
        "last_log_date": row.last_log_date.isoformat() if row.last_log_date else None,
    }


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
    }


def _serialize_component(row: fleet_models.AircraftComponent) -> dict[str, Any]:
    return {
        "id": row.id,
        "aircraft_serial_number": row.aircraft_serial_number,
        "position": row.position,
        "ata": row.ata,
        "part_number": row.part_number,
        "serial_number": row.serial_number,
        "description": row.description,
        "installed_date": row.installed_date.isoformat() if row.installed_date else None,
        "is_installed": bool(row.is_installed),
        "current_hours": float(row.current_hours) if row.current_hours is not None else None,
        "current_cycles": float(row.current_cycles) if row.current_cycles is not None else None,
    }


def _serialize_deferral(row: record_models.Deferral) -> dict[str, Any]:
    return {
        "id": row.id,
        "tail_id": row.tail_id,
        "defect_ref": row.defect_ref,
        "deferral_type": row.deferral_type,
        "deferred_at": row.deferred_at.isoformat(),
        "expiry_at": row.expiry_at.isoformat(),
        "status": row.status,
        "linked_wo_id": row.linked_wo_id,
        "linked_crs_id": row.linked_crs_id,
    }


def _normalize(dataset: str, payload: dict[str, Any], aircraft: Optional[fleet_models.Aircraft]) -> dict[str, Any]:
    tail_id = aircraft.serial_number if aircraft else _pick(payload, "aircraft_serial_number", "tail_id", "serial_number")
    registration = aircraft.registration if aircraft else _pick(payload, "registration", "aircraft_registration", "reg")
    if dataset == "AIRCRAFT_MASTER":
        return {
            "serial_number": str(_pick(payload, "serial_number", "msn", "aircraft_serial_number", default=tail_id) or ""),
            "registration": str(_pick(payload, "registration", "aircraft_registration", "reg", default=registration) or ""),
            "template": _pick(payload, "template", "aircraft_template", "type"),
            "make": _pick(payload, "make", "manufacturer"),
            "model": _pick(payload, "model", "series"),
            "home_base": _pick(payload, "home_base", "base", "station"),
            "status": str(_pick(payload, "status", default="OPEN")),
        }
    if dataset == "UTILISATION":
        return {
            "aircraft_serial_number": tail_id,
            "entry_date": _date(_pick(payload, "entry_date", "date", "log_date"), "entry_date").isoformat(),
            "techlog_no": str(_pick(payload, "techlog_no", "log_no", "flight_log_no")),
            "station": _pick(payload, "station", "base"),
            "total_hours": _number(_pick(payload, "total_hours", "ttaf", "aircraft_hours"), "total_hours"),
            "total_cycles": _number(_pick(payload, "total_cycles", "tca", "aircraft_cycles"), "total_cycles"),
            "block_hours": _number(payload["block_hours"], "block_hours") if payload.get("block_hours") is not None else None,
            "entry_cycles": _number(payload["entry_cycles"], "entry_cycles") if payload.get("entry_cycles") is not None else None,
            "remarks": _pick(payload, "remarks", "notes"),
        }
    if dataset == "COMPONENT":
        return {
            "aircraft_serial_number": tail_id,
            "position": str(_pick(payload, "position", "installed_position") or "").strip(),
            "ata": _pick(payload, "ata", "ata_chapter"),
            "part_number": str(_pick(payload, "part_number", "pn") or "").strip(),
            "serial_number": str(_pick(payload, "serial_number", "sn") or "").strip(),
            "description": _pick(payload, "description", "component_description"),
            "installed_date": _date(payload["installed_date"], "installed_date").isoformat() if payload.get("installed_date") else None,
            "is_installed": bool(_pick(payload, "is_installed", default=True)),
            "current_hours": _number(payload["current_hours"], "current_hours") if payload.get("current_hours") is not None else None,
            "current_cycles": _number(payload["current_cycles"], "current_cycles") if payload.get("current_cycles") is not None else None,
        }
    if dataset == "AMP_BASELINE":
        return {
            "aircraft_serial_number": tail_id,
            "revision_id": int(payload["revision_id"]) if payload.get("revision_id") is not None else None,
            "template_code": _pick(payload, "template_code", "template"),
            "revision_code": _pick(payload, "revision_code", "revision"),
            "notes": _pick(payload, "notes", "remarks"),
        }
    if dataset == "DEFERRAL":
        return {
            "tail_id": tail_id,
            "defect_ref": str(_pick(payload, "defect_ref", "defect_number", "reference") or "").strip(),
            "deferral_type": str(_pick(payload, "deferral_type", "type", default="MEL")),
            "deferred_at": _datetime(_pick(payload, "deferred_at", "raised_at", "date"), "deferred_at").isoformat(),
            "expiry_at": _datetime(_pick(payload, "expiry_at", "expires_at", "due_at"), "expiry_at").isoformat(),
            "status": str(_pick(payload, "status", default="Open")),
            "linked_wo_id": int(payload["linked_wo_id"]) if payload.get("linked_wo_id") else None,
            "linked_crs_id": int(payload["linked_crs_id"]) if payload.get("linked_crs_id") else None,
        }
    if dataset == "MAINTENANCE_RECORD":
        return {
            "tail_id": tail_id,
            "performed_at": _datetime(_pick(payload, "performed_at", "completion_date", "date"), "performed_at").isoformat(),
            "description": str(_pick(payload, "description", "work_performed") or "").strip(),
            "reference_data_text": str(_pick(payload, "reference_data_text", "reference", "maintenance_data") or "").strip(),
            "outcome": str(_pick(payload, "outcome", default="Completed")),
            "linked_wo_id": int(payload["linked_wo_id"]) if payload.get("linked_wo_id") else None,
            "linked_wp_id": str(payload["linked_wp_id"]) if payload.get("linked_wp_id") else None,
            "evidence_asset_ids": list(payload.get("evidence_asset_ids") or []),
        }
    raise ValueError(f"Unsupported dataset {dataset}")


def _required_errors(dataset: str, normalized: dict[str, Any]) -> list[str]:
    required = {
        "AIRCRAFT_MASTER": ("serial_number", "registration"),
        "UTILISATION": ("aircraft_serial_number", "entry_date", "techlog_no", "total_hours", "total_cycles"),
        "COMPONENT": ("aircraft_serial_number", "position", "part_number", "serial_number"),
        "AMP_BASELINE": ("aircraft_serial_number",),
        "DEFERRAL": ("tail_id", "defect_ref", "deferred_at", "expiry_at"),
        "MAINTENANCE_RECORD": ("tail_id", "performed_at", "description", "reference_data_text"),
    }[dataset]
    errors = [f"{field} is required" for field in required if normalized.get(field) in (None, "")]
    if dataset == "AMP_BASELINE" and not normalized.get("revision_id") and not (
        normalized.get("template_code") and normalized.get("revision_code")
    ):
        errors.append("revision_id or template_code plus revision_code is required")
    if dataset == "DEFERRAL" and normalized.get("deferred_at") and normalized.get("expiry_at"):
        if datetime.fromisoformat(normalized["expiry_at"]) <= datetime.fromisoformat(normalized["deferred_at"]):
            errors.append("expiry_at must be after deferred_at")
    return errors


def _summary(batch: MigrationBatch) -> dict[str, Any]:
    counter = Counter(row.status for row in batch.rows)
    datasets = Counter(row.dataset for row in batch.rows)
    open_recon = sum(1 for item in batch.reconciliation_items if item.status == MigrationReconciliationStatus.OPEN.value)
    checkpoint_counter = Counter(checkpoint.status for checkpoint in batch.checkpoints)
    return {
        "rows": len(batch.rows),
        "row_status": dict(counter),
        "datasets": dict(datasets),
        "open_reconciliation": open_recon,
        "checkpoints": dict(checkpoint_counter),
    }


def _refresh_summary(batch: MigrationBatch) -> None:
    batch.summary_json = _summary(batch)
    batch.cutover_checklist_json = {
        checkpoint.checkpoint_key: checkpoint.status for checkpoint in batch.checkpoints
    }


def batch_read(batch: MigrationBatch) -> MigrationBatchRead:
    _refresh_summary(batch)
    return MigrationBatchRead.model_validate(batch)


def list_batches(db: Session, *, amo_id: str) -> list[MigrationBatchRead]:
    batches = (
        db.query(MigrationBatch)
        .filter(MigrationBatch.amo_id == amo_id)
        .order_by(MigrationBatch.updated_at.desc())
        .all()
    )
    return [batch_read(batch) for batch in batches]


def create_batch(
    db: Session,
    *,
    amo_id: str,
    payload: MigrationBatchCreate,
    actor: User,
) -> MigrationBatch:
    duplicate = db.query(MigrationBatch).filter(MigrationBatch.amo_id == amo_id, MigrationBatch.name == payload.name).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Migration batch name already exists")
    batch = MigrationBatch(
        amo_id=amo_id,
        name=payload.name,
        preset=payload.preset,
        target_aircraft_serial_number=payload.target_aircraft_serial_number,
        target_registration=payload.target_registration,
        source_type=payload.source_type,
        source_reference=payload.source_reference,
        status=MigrationBatchStatus.DRAFT.value,
        mode="DRY_RUN",
        scope_json=payload.scope_json,
        summary_json={},
        cutover_checklist_json={},
        rollback_manifest_json=[],
        created_by_user_id=actor.id,
    )
    db.add(batch)
    db.flush()
    for key, label in PILOT_CHECKPOINTS:
        db.add(MigrationCheckpoint(amo_id=amo_id, batch_id=batch.id, checkpoint_key=key, label=label))
    db.flush()
    _refresh_summary(batch)
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor.id,
        entity_type="MigrationBatch",
        entity_id=batch.id,
        action="create",
        after={"name": batch.name, "target_registration": batch.target_registration},
    )
    return batch


def create_5y_sls_preset(
    db: Session,
    *,
    amo_id: str,
    payload: MigrationPresetCreate,
    actor: User,
) -> MigrationBatch:
    aircraft = (
        db.query(fleet_models.Aircraft)
        .filter(fleet_models.Aircraft.amo_id == amo_id, fleet_models.Aircraft.registration == "5Y-SLS")
        .first()
    )
    name = f"5Y-SLS pilot {date.today().isoformat()}"
    existing = db.query(MigrationBatch).filter(MigrationBatch.amo_id == amo_id, MigrationBatch.name == name).first()
    if existing:
        return existing
    return create_batch(
        db,
        amo_id=amo_id,
        payload=MigrationBatchCreate(
            name=name,
            preset="5Y-SLS-PILOT",
            target_aircraft_serial_number=aircraft.serial_number if aircraft else None,
            target_registration="5Y-SLS",
            source_type="SPREADSHEET",
            source_reference=payload.source_reference,
            scope_json=PILOT_SCOPE,
        ),
        actor=actor,
    )


def stage_rows(
    db: Session,
    *,
    batch: MigrationBatch,
    payload: MigrationStageRequest,
    actor: User,
) -> MigrationBatch:
    if batch.status not in {MigrationBatchStatus.DRAFT.value, MigrationBatchStatus.STAGED.value}:
        raise HTTPException(status_code=409, detail="Rows can only be staged into a draft or staged batch")
    if payload.replace_existing_stage:
        db.query(MigrationReconciliationItem).filter(MigrationReconciliationItem.batch_id == batch.id).delete(synchronize_session=False)
        db.query(MigrationRow).filter(MigrationRow.batch_id == batch.id).delete(synchronize_session=False)
        db.flush()
    start = db.query(MigrationRow).filter(MigrationRow.batch_id == batch.id).count()
    for offset, staged in enumerate(payload.rows, start=1):
        if staged.dataset not in SUPPORTED_DATASETS:
            raise HTTPException(status_code=400, detail=f"Unsupported migration dataset {staged.dataset}")
        duplicate = (
            db.query(MigrationRow)
            .filter(
                MigrationRow.batch_id == batch.id,
                MigrationRow.dataset == staged.dataset,
                MigrationRow.source_key == staged.source_key,
            )
            .first()
        )
        if duplicate:
            duplicate.raw_json = staged.payload
            duplicate.normalized_json = {}
            duplicate.status = MigrationRowStatus.STAGED.value
            duplicate.action = "PENDING"
            duplicate.errors_json = []
            duplicate.warnings_json = []
            db.add(duplicate)
            continue
        db.add(
            MigrationRow(
                amo_id=batch.amo_id,
                batch_id=batch.id,
                dataset=staged.dataset,
                source_row_number=start + offset,
                source_key=staged.source_key,
                raw_json=staged.payload,
                normalized_json={},
                status=MigrationRowStatus.STAGED.value,
                action="PENDING",
                errors_json=[],
                warnings_json=[],
            )
        )
    batch.status = MigrationBatchStatus.STAGED.value
    db.flush()
    _refresh_summary(batch)
    _audit(
        db,
        amo_id=batch.amo_id,
        actor_user_id=actor.id,
        entity_type="MigrationBatch",
        entity_id=batch.id,
        action="stage",
        after={"rows": len(payload.rows), "replace": payload.replace_existing_stage},
    )
    return batch


def validate_batch(db: Session, *, batch: MigrationBatch, actor: User) -> MigrationBatch:
    if batch.status not in {
        MigrationBatchStatus.STAGED.value,
        MigrationBatchStatus.VALIDATED.value,
        MigrationBatchStatus.RECONCILED.value,
    }:
        raise HTTPException(status_code=409, detail="Batch must contain staged rows before validation")
    aircraft = _target_aircraft(db, batch)
    for row in batch.rows:
        errors: list[str] = []
        warnings: list[str] = []
        try:
            normalized = _normalize(row.dataset, row.raw_json or {}, aircraft)
            errors.extend(_required_errors(row.dataset, normalized))
            if row.dataset != "AIRCRAFT_MASTER" and not aircraft:
                errors.append("target aircraft is not present in the tenant aircraft register")
            if row.dataset == "AIRCRAFT_MASTER" and batch.target_registration:
                if normalized.get("registration") != batch.target_registration:
                    errors.append("source registration does not match the migration batch target")
            row.normalized_json = normalized
        except Exception as exc:
            row.normalized_json = {}
            errors.append(str(exc))
        row.errors_json = errors
        row.warnings_json = warnings
        row.status = MigrationRowStatus.INVALID.value if errors else MigrationRowStatus.VALID.value
        row.action = "FIX_SOURCE" if errors else "RECONCILE"
        db.add(row)
    invalid = sum(1 for row in batch.rows if row.status == MigrationRowStatus.INVALID.value)
    batch.status = MigrationBatchStatus.VALIDATED.value if not invalid else MigrationBatchStatus.STAGED.value
    db.flush()
    _refresh_summary(batch)
    _audit(
        db,
        amo_id=batch.amo_id,
        actor_user_id=actor.id,
        entity_type="MigrationBatch",
        entity_id=batch.id,
        action="validate",
        after={"invalid": invalid, "rows": len(batch.rows)},
    )
    return batch


def _differences(source: dict[str, Any], local: dict[str, Any], ignore: Iterable[str] = ()) -> dict[str, Any]:
    ignored = set(ignore)
    differences: dict[str, Any] = {}
    for key, source_value in source.items():
        if key in ignored or source_value in (None, "", []):
            continue
        local_value = local.get(key)
        if isinstance(source_value, float) and local_value is not None:
            try:
                if abs(source_value - float(local_value)) <= 0.01:
                    continue
            except (TypeError, ValueError):
                pass
        if source_value != local_value:
            differences[key] = {"source": source_value, "local": local_value}
    return differences


def _recon_item(
    db: Session,
    *,
    batch: MigrationBatch,
    row: MigrationRow,
    category: str,
    summary: str,
    local: dict[str, Any],
    differences: dict[str, Any],
    severity: str = "ERROR",
) -> MigrationReconciliationItem:
    item = MigrationReconciliationItem(
        amo_id=batch.amo_id,
        batch_id=batch.id,
        row_id=row.id,
        category=category,
        severity=severity,
        status=MigrationReconciliationStatus.OPEN.value,
        summary=summary,
        source_json=row.normalized_json,
        local_json=local,
        differences_json=differences,
    )
    db.add(item)
    row.status = MigrationRowStatus.CONFLICT.value
    row.action = "RESOLVE"
    db.add(row)
    db.flush()
    return item


def _resolve_revision(db: Session, batch: MigrationBatch, normalized: dict[str, Any]) -> Optional[AmpProgramRevision]:
    query = db.query(AmpProgramRevision).filter(AmpProgramRevision.amo_id == batch.amo_id)
    if normalized.get("revision_id"):
        query = query.filter(AmpProgramRevision.id == normalized["revision_id"])
    else:
        query = query.filter(
            AmpProgramRevision.template_code == normalized.get("template_code"),
            AmpProgramRevision.revision_code == normalized.get("revision_code"),
        )
    return query.first()


def reconcile_batch(db: Session, *, batch: MigrationBatch, actor: User) -> MigrationBatch:
    if any(row.status == MigrationRowStatus.INVALID.value for row in batch.rows):
        raise HTTPException(status_code=409, detail="Resolve invalid source rows before reconciliation")
    if not batch.rows:
        raise HTTPException(status_code=409, detail="No migration rows are staged")
    db.query(MigrationReconciliationItem).filter(MigrationReconciliationItem.batch_id == batch.id).delete(synchronize_session=False)
    db.flush()
    aircraft = _target_aircraft(db, batch)
    for row in batch.rows:
        source = row.normalized_json or {}
        row.local_object_type = None
        row.local_object_id = None
        row.before_json = None
        row.after_json = None
        row.errors_json = []
        row.warnings_json = []
        row.status = MigrationRowStatus.READY.value
        row.action = "CREATE"

        if row.dataset == "AIRCRAFT_MASTER":
            local_aircraft = aircraft
            if not local_aircraft:
                row.action = "CREATE"
            else:
                local = _serialize_aircraft(local_aircraft)
                diffs = _differences(source, local, ignore=("status",))
                row.local_object_type = "Aircraft"
                row.local_object_id = local_aircraft.serial_number
                row.before_json = local
                if diffs:
                    _recon_item(db, batch=batch, row=row, category="AIRCRAFT_MASTER_MISMATCH", summary="Aircraft master differs from the controlled register", local=local, differences=diffs)
                else:
                    row.status = MigrationRowStatus.MATCHED.value
                    row.action = "MATCH"
        elif row.dataset == "UTILISATION":
            existing = (
                db.query(fleet_models.AircraftUsage)
                .filter(
                    fleet_models.AircraftUsage.amo_id == batch.amo_id,
                    fleet_models.AircraftUsage.aircraft_serial_number == source["aircraft_serial_number"],
                    fleet_models.AircraftUsage.date == date.fromisoformat(source["entry_date"]),
                    fleet_models.AircraftUsage.techlog_no == source["techlog_no"],
                )
                .first()
            )
            if existing:
                local = _serialize_usage(existing)
                diffs = _differences(source, local)
                row.local_object_type = "AircraftUsage"
                row.local_object_id = str(existing.id)
                row.before_json = local
                if diffs:
                    _recon_item(db, batch=batch, row=row, category="UTILISATION_MISMATCH", summary="Staged FH/FC differs from the immutable accepted ledger", local=local, differences=diffs)
                else:
                    row.status = MigrationRowStatus.MATCHED.value
                    row.action = "MATCH"
        elif row.dataset == "COMPONENT":
            existing = (
                db.query(fleet_models.AircraftComponent)
                .filter(
                    fleet_models.AircraftComponent.amo_id == batch.amo_id,
                    fleet_models.AircraftComponent.aircraft_serial_number == source["aircraft_serial_number"],
                    or_(
                        fleet_models.AircraftComponent.position == source["position"],
                        (
                            (fleet_models.AircraftComponent.part_number == source["part_number"])
                            & (fleet_models.AircraftComponent.serial_number == source["serial_number"])
                        ),
                    ),
                )
                .first()
            )
            if existing:
                local = _serialize_component(existing)
                diffs = _differences(source, local, ignore=("installed_date",))
                row.local_object_type = "AircraftComponent"
                row.local_object_id = str(existing.id)
                row.before_json = local
                if diffs:
                    _recon_item(db, batch=batch, row=row, category="COMPONENT_MISMATCH", summary="Installed component identity or position differs", local=local, differences=diffs)
                else:
                    row.status = MigrationRowStatus.MATCHED.value
                    row.action = "MATCH"
        elif row.dataset == "AMP_BASELINE":
            revision = _resolve_revision(db, batch, source)
            if not revision:
                _recon_item(db, batch=batch, row=row, category="AMP_REVISION_MISSING", summary="Referenced AMP revision is not registered", local={}, differences={"revision": {"source": source, "local": None}})
            elif revision.status != "APPROVED":
                _recon_item(db, batch=batch, row=row, category="AMP_REVISION_NOT_APPROVED", summary="Referenced AMP revision is not approved", local={"status": revision.status}, differences={"status": {"source": "APPROVED", "local": revision.status}})
            else:
                row.local_object_type = "AmpProgramRevision"
                row.local_object_id = str(revision.id)
                active = (
                    db.query(AmpAircraftBaseline)
                    .filter(
                        AmpAircraftBaseline.amo_id == batch.amo_id,
                        AmpAircraftBaseline.aircraft_serial_number == source["aircraft_serial_number"],
                        AmpAircraftBaseline.status == "ACTIVE",
                    )
                    .first()
                )
                if active and active.revision_id == revision.id:
                    row.status = MigrationRowStatus.MATCHED.value
                    row.action = "MATCH"
                elif active:
                    _recon_item(db, batch=batch, row=row, category="AMP_BASELINE_MISMATCH", summary="Aircraft is assigned to a different active AMP revision", local={"revision_id": active.revision_id, "template_code": active.template_code}, differences={"revision_id": {"source": revision.id, "local": active.revision_id}})
                else:
                    row.action = "APPLY_BASELINE"
        elif row.dataset == "DEFERRAL":
            existing = (
                db.query(record_models.Deferral)
                .filter(
                    record_models.Deferral.amo_id == batch.amo_id,
                    record_models.Deferral.tail_id == source["tail_id"],
                    record_models.Deferral.defect_ref == source["defect_ref"],
                )
                .first()
            )
            if existing:
                local = _serialize_deferral(existing)
                diffs = _differences(source, local)
                row.local_object_type = "Deferral"
                row.local_object_id = str(existing.id)
                row.before_json = local
                if diffs:
                    _recon_item(db, batch=batch, row=row, category="DEFERRAL_MISMATCH", summary="Deferred defect details or expiry differ", local=local, differences=diffs)
                else:
                    row.status = MigrationRowStatus.MATCHED.value
                    row.action = "MATCH"
        elif row.dataset == "MAINTENANCE_RECORD":
            performed_at = datetime.fromisoformat(source["performed_at"])
            existing = (
                db.query(record_models.MaintenanceRecord)
                .filter(
                    record_models.MaintenanceRecord.amo_id == batch.amo_id,
                    record_models.MaintenanceRecord.tail_id == source["tail_id"],
                    record_models.MaintenanceRecord.performed_at == performed_at,
                    record_models.MaintenanceRecord.description == source["description"],
                )
                .first()
            )
            if existing:
                row.local_object_type = "MaintenanceRecord"
                row.local_object_id = str(existing.id)
                row.status = MigrationRowStatus.MATCHED.value
                row.action = "MATCH"
        db.add(row)
    db.flush()
    open_errors = sum(
        1 for item in batch.reconciliation_items
        if item.status == MigrationReconciliationStatus.OPEN.value and item.severity == "ERROR"
    )
    batch.status = MigrationBatchStatus.RECONCILED.value
    db.flush()
    _refresh_summary(batch)
    _audit(
        db,
        amo_id=batch.amo_id,
        actor_user_id=actor.id,
        entity_type="MigrationBatch",
        entity_id=batch.id,
        action="reconcile",
        after={"open_errors": open_errors, "summary": batch.summary_json},
    )
    return batch


def decide_reconciliation(
    db: Session,
    *,
    batch: MigrationBatch,
    item_id: str,
    payload: MigrationReconciliationDecision,
    actor: User,
) -> MigrationReconciliationItem:
    item = (
        db.query(MigrationReconciliationItem)
        .filter(
            MigrationReconciliationItem.amo_id == batch.amo_id,
            MigrationReconciliationItem.batch_id == batch.id,
            MigrationReconciliationItem.id == item_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Migration reconciliation item not found")
    if item.status != MigrationReconciliationStatus.OPEN.value:
        raise HTTPException(status_code=409, detail="Reconciliation item is already resolved")
    row = item.row
    if payload.resolution == "KEEP_LOCAL":
        row.status = MigrationRowStatus.SKIPPED.value
        row.action = "KEEP_LOCAL"
    elif payload.resolution == "WAIVE":
        row.status = MigrationRowStatus.SKIPPED.value
        row.action = "WAIVE"
        item.status = MigrationReconciliationStatus.WAIVED.value
    else:
        row.normalized_json = payload.merged_payload if payload.resolution == "MERGE" else item.source_json
        row.status = MigrationRowStatus.READY.value
        row.action = "CREATE" if not row.local_object_id else "CONTROLLED_UPDATE"
    if item.status != MigrationReconciliationStatus.WAIVED.value:
        item.status = MigrationReconciliationStatus.RESOLVED.value
    item.resolution = payload.resolution
    item.resolution_notes = payload.resolution_notes
    item.resolved_by_user_id = actor.id
    item.resolved_at = _utcnow()
    db.add(row)
    db.add(item)
    db.flush()
    _refresh_summary(batch)
    _audit(
        db,
        amo_id=batch.amo_id,
        actor_user_id=actor.id,
        entity_type="MigrationReconciliationItem",
        entity_id=item.id,
        action="resolve",
        after={"resolution": item.resolution, "row_action": row.action},
    )
    return item


def update_checkpoint(
    db: Session,
    *,
    batch: MigrationBatch,
    checkpoint_key: str,
    payload: MigrationCheckpointUpdate,
    actor: User,
) -> MigrationCheckpoint:
    checkpoint = (
        db.query(MigrationCheckpoint)
        .filter(MigrationCheckpoint.batch_id == batch.id, MigrationCheckpoint.checkpoint_key == checkpoint_key)
        .first()
    )
    if not checkpoint:
        raise HTTPException(status_code=404, detail="Migration checkpoint not found")
    checkpoint.status = payload.status
    checkpoint.notes = payload.notes
    checkpoint.evidence_json = payload.evidence_json
    checkpoint.completed_by_user_id = actor.id if payload.status in {"COMPLETE", "NOT_APPLICABLE"} else None
    checkpoint.completed_at = _utcnow() if checkpoint.completed_by_user_id else None
    db.add(checkpoint)
    db.flush()
    _refresh_summary(batch)
    return checkpoint


def approve_batch(
    db: Session,
    *,
    batch: MigrationBatch,
    payload: MigrationApprovalRequest,
    actor: User,
) -> MigrationBatch:
    if batch.status != MigrationBatchStatus.RECONCILED.value:
        raise HTTPException(status_code=409, detail="Batch must be reconciled before approval")
    invalid = [row.id for row in batch.rows if row.status in {MigrationRowStatus.INVALID.value, MigrationRowStatus.CONFLICT.value}]
    open_errors = [
        item.id for item in batch.reconciliation_items
        if item.status == MigrationReconciliationStatus.OPEN.value and item.severity == "ERROR"
    ]
    incomplete = [
        checkpoint.checkpoint_key for checkpoint in batch.checkpoints
        if checkpoint.status not in {MigrationCheckpointStatus.COMPLETE.value, MigrationCheckpointStatus.NOT_APPLICABLE.value}
    ]
    if invalid or open_errors or incomplete:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Migration batch is not ready for approval.",
                "invalid_or_conflict_rows": invalid,
                "open_errors": open_errors,
                "incomplete_checkpoints": incomplete,
            },
        )
    batch.status = MigrationBatchStatus.APPROVED.value
    batch.approved_by_user_id = actor.id
    batch.approved_at = _utcnow()
    batch.scope_json = {**(batch.scope_json or {}), "approval_notes": payload.approval_notes}
    db.add(batch)
    _audit(
        db,
        amo_id=batch.amo_id,
        actor_user_id=actor.id,
        entity_type="MigrationBatch",
        entity_id=batch.id,
        action="approve",
        after={"approval_notes": payload.approval_notes},
    )
    return batch


def _append_rollback(batch: MigrationBatch, entry: dict[str, Any]) -> None:
    manifest = list(batch.rollback_manifest_json or [])
    manifest.append(entry)
    batch.rollback_manifest_json = manifest


def _commit_row(db: Session, *, batch: MigrationBatch, row: MigrationRow, actor: User) -> None:
    source = row.normalized_json or {}
    if row.status in {MigrationRowStatus.MATCHED.value, MigrationRowStatus.SKIPPED.value}:
        row.status = MigrationRowStatus.SKIPPED.value
        row.applied_at = _utcnow()
        return
    if row.action == "CONTROLLED_UPDATE":
        row.status = MigrationRowStatus.SKIPPED.value
        row.errors_json = ["Existing controlled records require their native correction workflow; automatic overwrite was blocked."]
        row.applied_at = _utcnow()
        return
    if row.dataset == "AIRCRAFT_MASTER":
        existing = _target_aircraft(db, batch)
        if existing:
            for field in ("template", "make", "model", "home_base"):
                if getattr(existing, field) in (None, "") and source.get(field):
                    setattr(existing, field, source[field])
            db.add(existing)
            row.local_object_type = "Aircraft"
            row.local_object_id = existing.serial_number
            row.after_json = _serialize_aircraft(existing)
        else:
            aircraft = fleet_models.Aircraft(
                amo_id=batch.amo_id,
                serial_number=source["serial_number"],
                registration=source["registration"],
                template=source.get("template"),
                make=source.get("make"),
                model=source.get("model"),
                home_base=source.get("home_base"),
                status=source.get("status") or "OPEN",
                is_active=True,
            )
            db.add(aircraft)
            db.flush()
            batch.target_aircraft_serial_number = aircraft.serial_number
            row.local_object_type = "Aircraft"
            row.local_object_id = aircraft.serial_number
            row.after_json = _serialize_aircraft(aircraft)
            _append_rollback(batch, {"object_type": "Aircraft", "object_id": aircraft.serial_number, "row_id": row.id, "reversible": True})
    elif row.dataset == "UTILISATION":
        usage = control_services.create_canonical_utilisation(
            db,
            amo_id=batch.amo_id,
            actor_user_id=actor.id,
            aircraft_serial_number=source["aircraft_serial_number"],
            payload=CanonicalUtilisationCreate(
                tail_id=source["aircraft_serial_number"],
                entry_date=date.fromisoformat(source["entry_date"]),
                techlog_no=source["techlog_no"],
                station=source.get("station"),
                hours=float(source["total_hours"]),
                cycles=float(source["total_cycles"]),
                block_hours=source.get("block_hours"),
                entry_cycles=source.get("entry_cycles"),
                source="MIGRATION",
                remarks=source.get("remarks"),
                note=f"Migration batch {batch.id}; source {row.source_key}",
            ),
        )
        row.local_object_type = "AircraftUsage"
        row.local_object_id = str(usage.id)
        row.after_json = _serialize_usage(usage)
        _append_rollback(batch, {"object_type": "AircraftUsage", "object_id": str(usage.id), "row_id": row.id, "aircraft_serial_number": usage.aircraft_serial_number, "reversible": True})
    elif row.dataset == "COMPONENT":
        component = fleet_models.AircraftComponent(
            amo_id=batch.amo_id,
            aircraft_serial_number=source["aircraft_serial_number"],
            position=source["position"],
            ata=source.get("ata"),
            part_number=source["part_number"],
            serial_number=source["serial_number"],
            description=source.get("description"),
            installed_date=date.fromisoformat(source["installed_date"]) if source.get("installed_date") else None,
            is_installed=bool(source.get("is_installed", True)),
            current_hours=source.get("current_hours"),
            current_cycles=source.get("current_cycles"),
            verification_status="MIGRATED_PENDING_VERIFICATION",
        )
        db.add(component)
        db.flush()
        row.local_object_type = "AircraftComponent"
        row.local_object_id = str(component.id)
        row.after_json = _serialize_component(component)
        _append_rollback(batch, {"object_type": "AircraftComponent", "object_id": str(component.id), "row_id": row.id, "reversible": True})
    elif row.dataset == "AMP_BASELINE":
        revision = _resolve_revision(db, batch, source)
        if not revision:
            raise ValueError("AMP revision could not be resolved during commit")
        result = revision_services.apply_revision_to_aircraft(
            db,
            revision=revision,
            aircraft_serial_number=source["aircraft_serial_number"],
            notes=f"Migration batch {batch.id}: {source.get('notes') or ''}".strip(),
            actor=actor,
        )
        row.local_object_type = "AmpAircraftBaseline"
        row.local_object_id = str(result.id)
        row.after_json = result.model_dump(mode="json")
        _append_rollback(batch, {"object_type": "AmpAircraftBaseline", "object_id": str(result.id), "row_id": row.id, "reversible": False, "reason": "Previous baseline supersedure requires controlled manual restoration"})
    elif row.dataset == "DEFERRAL":
        deferral = record_models.Deferral(
            amo_id=batch.amo_id,
            tail_id=source["tail_id"],
            defect_ref=source["defect_ref"],
            deferral_type=source["deferral_type"],
            deferred_at=datetime.fromisoformat(source["deferred_at"]),
            expiry_at=datetime.fromisoformat(source["expiry_at"]),
            status=source["status"],
            linked_wo_id=source.get("linked_wo_id"),
            linked_crs_id=source.get("linked_crs_id"),
            extension_history_json=[],
        )
        db.add(deferral)
        db.flush()
        row.local_object_type = "Deferral"
        row.local_object_id = str(deferral.id)
        row.after_json = _serialize_deferral(deferral)
        _append_rollback(batch, {"object_type": "Deferral", "object_id": str(deferral.id), "row_id": row.id, "reversible": True})
    elif row.dataset == "MAINTENANCE_RECORD":
        record = record_models.MaintenanceRecord(
            amo_id=batch.amo_id,
            tail_id=source["tail_id"],
            performed_at=datetime.fromisoformat(source["performed_at"]),
            description=source["description"],
            reference_data_text=source["reference_data_text"],
            certifying_user_id=None,
            outcome=source["outcome"],
            linked_wo_id=source.get("linked_wo_id"),
            linked_wp_id=source.get("linked_wp_id"),
            evidence_asset_ids=source.get("evidence_asset_ids") or [],
        )
        db.add(record)
        db.flush()
        row.local_object_type = "MaintenanceRecord"
        row.local_object_id = str(record.id)
        row.after_json = {"id": record.id, **source}
        _append_rollback(batch, {"object_type": "MaintenanceRecord", "object_id": str(record.id), "row_id": row.id, "reversible": True})
    row.status = MigrationRowStatus.APPLIED.value
    row.applied_at = _utcnow()
    db.add(row)


def commit_batch(
    db: Session,
    *,
    batch: MigrationBatch,
    payload: MigrationCommitRequest,
    actor: User,
) -> MigrationBatch:
    if batch.status != MigrationBatchStatus.APPROVED.value:
        raise HTTPException(status_code=409, detail="Migration batch must be approved before commit")
    failures: list[dict[str, str]] = []
    for row in sorted(batch.rows, key=lambda item: (item.dataset, item.source_row_number)):
        try:
            _commit_row(db, batch=batch, row=row, actor=actor)
            db.flush()
        except Exception as exc:
            row.status = MigrationRowStatus.FAILED.value
            row.errors_json = [str(exc)]
            db.add(row)
            failures.append({"row_id": row.id, "error": str(exc)})
            if not payload.allow_partial:
                raise HTTPException(
                    status_code=409,
                    detail={"message": "Migration commit stopped at the first failed row.", "failure": failures[-1]},
                ) from exc
    batch.status = MigrationBatchStatus.PARTIAL.value if failures else MigrationBatchStatus.COMMITTED.value
    batch.mode = "COMMIT"
    batch.committed_by_user_id = actor.id
    batch.committed_at = _utcnow()
    batch.scope_json = {**(batch.scope_json or {}), "commit_notes": payload.commit_notes}
    db.add(batch)
    db.flush()
    _refresh_summary(batch)
    _audit(
        db,
        amo_id=batch.amo_id,
        actor_user_id=actor.id,
        entity_type="MigrationBatch",
        entity_id=batch.id,
        action="commit",
        after={"status": batch.status, "failures": failures, "summary": batch.summary_json},
    )
    return batch


def rollback_batch(
    db: Session,
    *,
    batch: MigrationBatch,
    payload: MigrationRollbackRequest,
    actor: User,
) -> MigrationBatch:
    if batch.status not in {MigrationBatchStatus.COMMITTED.value, MigrationBatchStatus.PARTIAL.value}:
        raise HTTPException(status_code=409, detail="Only committed or partial batches can be rolled back")
    irreversible = [entry for entry in batch.rollback_manifest_json or [] if not entry.get("reversible")]
    if irreversible:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Automatic rollback is blocked because the batch contains controlled irreversible actions.",
                "manual_restoration": irreversible,
            },
        )
    affected_aircraft: set[str] = set()
    for entry in reversed(batch.rollback_manifest_json or []):
        object_type = entry["object_type"]
        object_id = entry["object_id"]
        if object_type == "AircraftUsage":
            row = db.get(fleet_models.AircraftUsage, int(object_id))
            if row:
                affected_aircraft.add(row.aircraft_serial_number)
                db.delete(row)
        elif object_type == "AircraftComponent":
            row = db.get(fleet_models.AircraftComponent, int(object_id))
            if row:
                db.delete(row)
        elif object_type == "Deferral":
            row = db.get(record_models.Deferral, int(object_id))
            if row:
                db.delete(row)
        elif object_type == "MaintenanceRecord":
            row = db.get(record_models.MaintenanceRecord, int(object_id))
            if row:
                db.delete(row)
        elif object_type == "Aircraft":
            row = db.query(fleet_models.Aircraft).filter(fleet_models.Aircraft.serial_number == object_id).first()
            if row:
                db.delete(row)
        migration_row = db.get(MigrationRow, entry["row_id"])
        if migration_row:
            migration_row.status = MigrationRowStatus.ROLLED_BACK.value
            db.add(migration_row)
    db.flush()
    for aircraft_serial_number in affected_aircraft:
        control_services.recalculate_usage_chain(db, amo_id=batch.amo_id, aircraft_serial_number=aircraft_serial_number)
    batch.status = MigrationBatchStatus.ROLLED_BACK.value
    batch.scope_json = {**(batch.scope_json or {}), "rollback_reason": payload.reason}
    db.add(batch)
    db.flush()
    _refresh_summary(batch)
    _audit(
        db,
        amo_id=batch.amo_id,
        actor_user_id=actor.id,
        entity_type="MigrationBatch",
        entity_id=batch.id,
        action="rollback",
        after={"reason": payload.reason, "affected_aircraft": sorted(affected_aircraft)},
    )
    return batch


def summary(db: Session, *, amo_id: str) -> MigrationSummaryRead:
    batches = db.query(MigrationBatch).filter(MigrationBatch.amo_id == amo_id).all()
    latest = max(batches, key=lambda batch: batch.updated_at) if batches else None
    return MigrationSummaryRead(
        batches=len(batches),
        active_batches=sum(
            1 for batch in batches
            if batch.status not in {
                MigrationBatchStatus.COMMITTED.value,
                MigrationBatchStatus.ROLLED_BACK.value,
                MigrationBatchStatus.CANCELLED.value,
            }
        ),
        open_reconciliation=db.query(MigrationReconciliationItem).filter(
            MigrationReconciliationItem.amo_id == amo_id,
            MigrationReconciliationItem.status == MigrationReconciliationStatus.OPEN.value,
        ).count(),
        staged_rows=db.query(MigrationRow).filter(
            MigrationRow.amo_id == amo_id,
            MigrationRow.status.in_([
                MigrationRowStatus.STAGED.value,
                MigrationRowStatus.VALID.value,
                MigrationRowStatus.READY.value,
            ]),
        ).count(),
        applied_rows=db.query(MigrationRow).filter(
            MigrationRow.amo_id == amo_id,
            MigrationRow.status == MigrationRowStatus.APPLIED.value,
        ).count(),
        failed_rows=db.query(MigrationRow).filter(
            MigrationRow.amo_id == amo_id,
            MigrationRow.status.in_([MigrationRowStatus.INVALID.value, MigrationRowStatus.FAILED.value]),
        ).count(),
        latest_batch=batch_read(latest) if latest else None,
    )
