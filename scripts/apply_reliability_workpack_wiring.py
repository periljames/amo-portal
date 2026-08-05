from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


WORKPACK_INTEGRATION = r'''from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.work import models as work_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user
from amodb.utils.identifiers import generate_uuid7

from . import advanced_models as domain
from . import advanced_schemas as schemas
from . import advanced_services as services
from . import models as legacy


class InternalSourceSpec(BaseModel):
    code: str
    name: str
    source_type: schemas.ReliabilitySourceType
    transport: str
    module: str
    dataset: str
    authoritative_tables: List[str]
    manual_fallback: bool = True


INTERNAL_SOURCE_SPECS: tuple[InternalSourceSpec, ...] = (
    InternalSourceSpec(
        code="WORKPACK-TASKS",
        name="Workpack defects and non-routine findings",
        source_type="MAINTENANCE",
        transport="INTERNAL",
        module="Workpack / Work Orders",
        dataset="Defect and non-routine task cards",
        authoritative_tables=["work_orders", "task_cards"],
    ),
    InternalSourceSpec(
        code="COMPONENT-REMOVALS",
        name="Component removals and swaps",
        source_type="COMPONENT_SHOP",
        transport="INTERNAL",
        module="Components / Stores / Workpack",
        dataset="Removal events and part movements",
        authoritative_tables=["removal_events", "part_movement_ledger", "component_instances"],
    ),
    InternalSourceSpec(
        code="TECH-RECORDS-USAGE",
        name="Aircraft utilisation exposure",
        source_type="TECH_RECORDS",
        transport="INTERNAL",
        module="Technical Records / Fleet",
        dataset="Daily aircraft flight hours and cycles",
        authoritative_tables=["aircraft_usage"],
    ),
    InternalSourceSpec(
        code="EHM-INTERNAL",
        name="Engine health trend shifts",
        source_type="EHM",
        transport="INTERNAL",
        module="Engine Health Monitoring",
        dataset="Engine trend status shifts",
        authoritative_tables=["engine_trend_status"],
    ),
    InternalSourceSpec(
        code="MANUAL-ENTRY",
        name="Controlled manual Reliability entry",
        source_type="MANUAL",
        transport="PUSH",
        module="Reliability",
        dataset="Human-entered occurrences with source justification",
        authoritative_tables=["reliability_ingestion_records", "reliability_events"],
    ),
)


class ManualReliabilityEntry(BaseModel):
    event_type: str
    occurred_at: datetime
    description: str = Field(min_length=3, max_length=12000)
    submitted_reason: str = Field(min_length=3, max_length=2000)
    source_reference: Optional[str] = Field(default=None, max_length=255)
    severity: str = "MEDIUM"
    aircraft_serial_number: Optional[str] = Field(default=None, max_length=50)
    work_order_id: Optional[int] = Field(default=None, ge=1)
    task_card_id: Optional[int] = Field(default=None, ge=1)
    component_id: Optional[int] = Field(default=None, ge=1)
    ata_chapter: Optional[str] = Field(default=None, max_length=20)
    reference_code: Optional[str] = Field(default=None, max_length=64)
    engine_position: Optional[str] = Field(default=None, max_length=32)
    flight_number: Optional[str] = Field(default=None, max_length=24)
    origin_station: Optional[str] = Field(default=None, max_length=8)
    destination_station: Optional[str] = Field(default=None, max_length=8)
    delay_minutes: Optional[int] = Field(default=None, ge=0, le=2147483647)
    mel_reference: Optional[str] = Field(default=None, max_length=80)
    cdl_reference: Optional[str] = Field(default=None, max_length=80)
    deferral_expires_at: Optional[datetime] = None
    part_number: Optional[str] = Field(default=None, max_length=80)
    component_serial_number: Optional[str] = Field(default=None, max_length=80)
    confirmed_failure: Optional[bool] = None
    repeat_key: Optional[str] = Field(default=None, max_length=255)
    extra_fields: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        resolved = services.EVENT_ALIASES.get(value.strip().upper(), value.strip().upper())
        valid = {item.value for item in legacy.ReliabilityEventTypeEnum}
        if resolved not in valid:
            raise ValueError("Unsupported Reliability event type.")
        return resolved

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        resolved = value.strip().upper()
        valid = {item.value for item in legacy.ReliabilitySeverityEnum}
        if resolved not in valid:
            raise ValueError("Unsupported Reliability severity.")
        return resolved


class InternalSourceCoverageItem(BaseModel):
    code: str
    module: str
    dataset: str
    source_id: Optional[str] = None
    source_status: str
    integration_status: str
    record_count: int
    latest_record_at: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    manual_fallback: bool
    detail: str


class InternalSourceCoverage(BaseModel):
    generated_at: datetime
    items: List[InternalSourceCoverageItem]


_ORIGINAL_BOOTSTRAP = services.bootstrap_reliability
_REGISTERED = False


def _enum_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _date_as_utc(value: Optional[date]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


def _source_configuration(spec: InternalSourceSpec) -> Dict[str, Any]:
    return {
        "adapter": "canonical-internal-v1",
        "module": spec.module,
        "dataset": spec.dataset,
        "authoritative_tables": spec.authoritative_tables,
        "canonical_contract": "reliability-event-v1",
        "manual_fallback": spec.manual_fallback,
        "reserved_source": True,
    }


def _ensure_source(
    db: Session,
    *,
    amo_id: str,
    spec: InternalSourceSpec,
    actor_user_id: str,
) -> tuple[domain.ReliabilitySource, bool]:
    source = (
        db.query(domain.ReliabilitySource)
        .filter(domain.ReliabilitySource.amo_id == amo_id, domain.ReliabilitySource.code == spec.code)
        .first()
    )
    if source:
        changed = False
        expected = {
            "name": spec.name,
            "source_type": spec.source_type,
            "transport": spec.transport,
            "mapping_version": "canonical-internal-v1" if spec.transport == "INTERNAL" else "manual-v1",
            "status": "ACTIVE",
        }
        for field, value in expected.items():
            if getattr(source, field) != value:
                setattr(source, field, value)
                changed = True
        configuration = {**(source.configuration_json or {}), **_source_configuration(spec)}
        if configuration != (source.configuration_json or {}):
            source.configuration_json = configuration
            changed = True
        if changed:
            services.append_audit(
                db,
                amo_id=amo_id,
                entity_type="SOURCE",
                entity_id=source.id,
                action="RESERVED_SOURCE_CONFIGURED",
                payload={"code": spec.code, "adapter": "canonical-internal-v1"},
                actor_user_id=actor_user_id,
            )
            db.commit()
            db.refresh(source)
        return source, False

    source = services.create_source(
        db,
        amo_id=amo_id,
        payload=schemas.ReliabilitySourceCreate(
            code=spec.code,
            name=spec.name,
            source_type=spec.source_type,
            transport=spec.transport,  # type: ignore[arg-type]
            mapping_version="canonical-internal-v1" if spec.transport == "INTERNAL" else "manual-v1",
            configuration_json=_source_configuration(spec),
            poll_interval_minutes=60 if spec.transport == "INTERNAL" else None,
        ),
        actor_user_id=actor_user_id,
    )
    return source, True


def ensure_reserved_sources(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
) -> tuple[Dict[str, domain.ReliabilitySource], int]:
    sources: Dict[str, domain.ReliabilitySource] = {}
    created = 0
    for spec in INTERNAL_SOURCE_SPECS:
        source, was_created = _ensure_source(
            db,
            amo_id=amo_id,
            spec=spec,
            actor_user_id=actor_user_id,
        )
        sources[spec.code] = source
        created += int(was_created)
    return sources, created


def bootstrap_reliability(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
) -> schemas.BootstrapResult:
    result = _ORIGINAL_BOOTSTRAP(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
    )
    sources, created = ensure_reserved_sources(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
    )
    source_ids = list(dict.fromkeys([*result.source_ids, *(item.id for item in sources.values())]))
    created_map = dict(result.created)
    created_map["sources"] = int(created_map.get("sources", 0)) + created
    return result.model_copy(update={"source_ids": source_ids, "created": created_map})


def _task_is_reliability_relevant(task: work_models.TaskCard) -> bool:
    category = _enum_value(task.category)
    origin = _enum_value(task.origin_type)
    return category in {"DEFECT", "UNSCHEDULED"} or origin == "NON_ROUTINE"


def _task_record(task: work_models.TaskCard) -> Dict[str, Any]:
    work_order = task.work_order
    occurred_at = _as_utc(task.actual_end) or _as_utc(task.actual_start) or _as_utc(task.updated_at) or _as_utc(task.created_at)
    revision_at = _as_utc(task.updated_at) or _as_utc(task.created_at) or occurred_at
    category = _enum_value(task.category)
    origin = _enum_value(task.origin_type)
    priority = _enum_value(task.priority) or "MEDIUM"
    severity = {"CRITICAL": "CRITICAL", "HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}.get(priority, "MEDIUM")
    text = f"{task.title} {task.description or ''}".upper()
    event_type = "REPEAT_DEFECT" if any(token in text for token in ("REPEAT", "RECURR", "REPETITIVE")) else "DEFECT"
    component = getattr(task, "component", None)
    reference_code = task.task_code or f"WO-{work_order.wo_number}-TC-{task.id}"
    repeat_key = f"{task.aircraft_serial_number}:{task.ata_chapter or 'UNK'}:{task.task_code or task.title}"[:255]
    return {
        "external_id": f"WORKPACK_TASK:{task.id}:{revision_at.isoformat() if revision_at else 'UNKNOWN'}",
        "event_type": event_type,
        "occurred_at": occurred_at.isoformat() if occurred_at else datetime.now(timezone.utc).isoformat(),
        "aircraft_serial_number": task.aircraft_serial_number,
        "work_order_id": task.work_order_id,
        "task_card_id": task.id,
        "component_id": task.aircraft_component_id,
        "ata_chapter": task.ata_chapter,
        "reference_code": reference_code,
        "operator_event_id": task.operator_event_id or work_order.operator_event_id,
        "severity": severity,
        "description": task.description or task.title,
        "part_number": getattr(component, "part_number", None),
        "component_serial_number": getattr(component, "serial_number", None),
        "repeat_key": repeat_key,
        "operation_stage": f"WORKPACK:{_enum_value(work_order.status)}/TASK:{_enum_value(task.status)}",
        "work_package_ref": work_order.work_package_ref,
        "work_order_number": work_order.wo_number,
        "check_type": work_order.check_type,
        "task_category": category,
        "task_origin": origin,
        "task_status": _enum_value(task.status),
        "parent_task_id": task.parent_task_id,
        "program_item_id": task.program_item_id,
        "source_updated_at": revision_at.isoformat() if revision_at else None,
    }


def _workpack_records(db: Session, *, amo_id: str, cursor: datetime) -> List[Dict[str, Any]]:
    rows = (
        db.query(work_models.TaskCard)
        .join(work_models.WorkOrder, work_models.TaskCard.work_order_id == work_models.WorkOrder.id)
        .filter(
            work_models.TaskCard.amo_id == amo_id,
            work_models.WorkOrder.amo_id == amo_id,
            or_(work_models.TaskCard.updated_at > cursor, work_models.TaskCard.created_at > cursor),
        )
        .order_by(work_models.TaskCard.updated_at.asc(), work_models.TaskCard.id.asc())
        .limit(5000)
        .all()
    )
    return [_task_record(task) for task in rows if _task_is_reliability_relevant(task)]


def _removal_record(
    removal: legacy.RemovalEvent,
    movement: Optional[legacy.PartMovementLedger],
    instance: Optional[legacy.ComponentInstance],
) -> Dict[str, Any]:
    reason = (removal.removal_reason or "").upper()
    scheduled = any(token in reason for token in ("SCHEDULED", "PLANNED", "LIFE LIMIT", "TIME EXPIRED", "TBO"))
    event_type = "SCHEDULED_REMOVAL" if scheduled else "UNSCHEDULED_REMOVAL"
    return {
        "external_id": f"REMOVAL_EVENT:{removal.id}",
        "event_type": event_type,
        "occurred_at": _as_utc(removal.removed_at).isoformat(),
        "aircraft_serial_number": removal.aircraft_serial_number,
        "component_id": removal.component_id,
        "work_order_id": movement.work_order_id if movement else None,
        "task_card_id": movement.task_card_id if movement else None,
        "reference_code": removal.removal_tracking_id,
        "severity": "MEDIUM" if scheduled else "HIGH",
        "description": removal.removal_reason or f"{event_type.replace('_', ' ').title()} recorded",
        "part_number": instance.part_number if instance else None,
        "component_serial_number": instance.serial_number if instance else None,
        "confirmed_failure": None,
        "removal_tracking_id": removal.removal_tracking_id,
        "removal_reason": removal.removal_reason,
        "hours_at_removal": removal.hours_at_removal,
        "cycles_at_removal": removal.cycles_at_removal,
        "part_movement_id": removal.part_movement_id,
        "component_instance_id": removal.component_instance_id,
        "movement_reason_code": movement.reason_code if movement else None,
        "movement_notes": movement.notes if movement else None,
    }


def _component_records(db: Session, *, amo_id: str, cursor: datetime) -> List[Dict[str, Any]]:
    removals = (
        db.query(legacy.RemovalEvent)
        .filter(
            legacy.RemovalEvent.amo_id == amo_id,
            or_(legacy.RemovalEvent.created_at > cursor, legacy.RemovalEvent.removed_at > cursor),
        )
        .order_by(legacy.RemovalEvent.removed_at.asc(), legacy.RemovalEvent.id.asc())
        .limit(5000)
        .all()
    )
    movement_ids = [item.part_movement_id for item in removals if item.part_movement_id]
    instance_ids = [item.component_instance_id for item in removals if item.component_instance_id]
    movements = {
        item.id: item
        for item in db.query(legacy.PartMovementLedger)
        .filter(legacy.PartMovementLedger.amo_id == amo_id, legacy.PartMovementLedger.id.in_(movement_ids or [-1]))
        .all()
    }
    instances = {
        item.id: item
        for item in db.query(legacy.ComponentInstance)
        .filter(legacy.ComponentInstance.amo_id == amo_id, legacy.ComponentInstance.id.in_(instance_ids or [-1]))
        .all()
    }
    return [
        _removal_record(item, movements.get(item.part_movement_id), instances.get(item.component_instance_id))
        for item in removals
    ]


def _ehm_records(db: Session, *, amo_id: str, cursor: datetime) -> List[Dict[str, Any]]:
    shifts = (
        db.query(legacy.EngineTrendStatus)
        .filter(
            legacy.EngineTrendStatus.amo_id == amo_id,
            legacy.EngineTrendStatus.current_status == legacy.EngineTrendStatusEnum.SHIFT,
            legacy.EngineTrendStatus.updated_at > cursor,
        )
        .order_by(legacy.EngineTrendStatus.updated_at.asc(), legacy.EngineTrendStatus.id.asc())
        .limit(5000)
        .all()
    )
    return [
        {
            "external_id": f"ENGINE_SHIFT:{shift.id}:{_as_utc(shift.updated_at).isoformat()}",
            "event_type": "EHM_ALERT",
            "occurred_at": _as_utc(shift.updated_at).isoformat(),
            "aircraft_serial_number": shift.aircraft_serial_number,
            "engine_position": shift.engine_position,
            "severity": "HIGH",
            "description": f"Engine trend shift for {shift.engine_position}",
            "engine_serial_number": shift.engine_serial_number,
            "last_upload_date": shift.last_upload_date.isoformat() if shift.last_upload_date else None,
            "last_trend_date": shift.last_trend_date.isoformat() if shift.last_trend_date else None,
        }
        for shift in shifts
    ]


def _usage_latest(db: Session, *, amo_id: str) -> tuple[int, Optional[date]]:
    count, latest = db.query(
        func.count(fleet_models.AircraftUsage.id),
        func.max(fleet_models.AircraftUsage.date),
    ).filter(fleet_models.AircraftUsage.amo_id == amo_id).one()
    return int(count or 0), latest


def harvest_internal_sources(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str] = None,
) -> List[schemas.ReliabilityIngestionResult]:
    if not actor_user_id:
        raise HTTPException(status_code=400, detail="An accountable actor is required for internal Reliability sync.")
    sources, _ = ensure_reserved_sources(db, amo_id=amo_id, actor_user_id=actor_user_id)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    builders = {
        "WORKPACK-TASKS": _workpack_records,
        "COMPONENT-REMOVALS": _component_records,
        "EHM-INTERNAL": _ehm_records,
    }
    results: List[schemas.ReliabilityIngestionResult] = []
    for code, builder in builders.items():
        source = sources[code]
        cursor = _as_utc(source.last_success_at) or epoch
        records = builder(db, amo_id=amo_id, cursor=cursor)
        if records:
            results.append(
                services.ingest_batch(
                    db,
                    amo_id=amo_id,
                    source=source,
                    payload=schemas.ReliabilityBatchIngest(
                        records=records,
                        metadata_json={
                            "adapter": "canonical-internal-v1",
                            "source_code": code,
                            "cursor": cursor.isoformat(),
                            "authoritative_tables": source.configuration_json.get("authoritative_tables", []),
                        },
                    ),
                    actor_user_id=actor_user_id,
                )
            )
        else:
            source.next_poll_at = datetime.now(timezone.utc)
            db.commit()

    usage_source = sources["TECH-RECORDS-USAGE"]
    usage_count, latest_usage = _usage_latest(db, amo_id=amo_id)
    if usage_count and latest_usage:
        latest_at = _date_as_utc(latest_usage)
        usage_source.last_received_at = latest_at
        usage_source.last_success_at = datetime.now(timezone.utc)
        usage_source.last_cursor = latest_usage.isoformat()
        db.commit()
    return results


def _hydrate_manual_links(
    db: Session,
    *,
    amo_id: str,
    payload: ManualReliabilityEntry,
) -> Dict[str, Any]:
    values = payload.model_dump(mode="json")
    work_order = None
    task = None
    if payload.work_order_id:
        work_order = (
            db.query(work_models.WorkOrder)
            .filter(work_models.WorkOrder.amo_id == amo_id, work_models.WorkOrder.id == payload.work_order_id)
            .first()
        )
        if not work_order:
            raise HTTPException(status_code=422, detail="The selected work order does not exist in this tenant.")
    if payload.task_card_id:
        task = (
            db.query(work_models.TaskCard)
            .filter(work_models.TaskCard.amo_id == amo_id, work_models.TaskCard.id == payload.task_card_id)
            .first()
        )
        if not task:
            raise HTTPException(status_code=422, detail="The selected task card does not exist in this tenant.")
        if work_order and task.work_order_id != work_order.id:
            raise HTTPException(status_code=422, detail="The task card does not belong to the selected work order.")
        work_order = work_order or task.work_order
        values["work_order_id"] = task.work_order_id
        values["aircraft_serial_number"] = values.get("aircraft_serial_number") or task.aircraft_serial_number
        values["ata_chapter"] = values.get("ata_chapter") or task.ata_chapter
        values["component_id"] = values.get("component_id") or task.aircraft_component_id
        values["reference_code"] = values.get("reference_code") or task.task_code
        values["repeat_key"] = values.get("repeat_key") or f"{task.aircraft_serial_number}:{task.ata_chapter or 'UNK'}:{task.task_code or task.title}"[:255]
    if work_order:
        values["aircraft_serial_number"] = values.get("aircraft_serial_number") or work_order.aircraft_serial_number
        values["work_package_ref"] = work_order.work_package_ref
        values["work_order_number"] = work_order.wo_number
        values["check_type"] = work_order.check_type
    if values.get("aircraft_serial_number"):
        aircraft = (
            db.query(fleet_models.Aircraft)
            .filter(
                fleet_models.Aircraft.amo_id == amo_id,
                fleet_models.Aircraft.serial_number == values["aircraft_serial_number"],
            )
            .first()
        )
        if not aircraft:
            raise HTTPException(status_code=422, detail="The selected aircraft does not exist in this tenant.")
    return values


def create_manual_entry(
    db: Session,
    *,
    amo_id: str,
    payload: ManualReliabilityEntry,
    actor_user_id: str,
) -> schemas.ReliabilityIngestionResult:
    sources, _ = ensure_reserved_sources(db, amo_id=amo_id, actor_user_id=actor_user_id)
    values = _hydrate_manual_links(db, amo_id=amo_id, payload=payload)
    manual_id = generate_uuid7()
    extra_fields = dict(values.pop("extra_fields", {}) or {})
    source_reference = values.pop("source_reference", None)
    submitted_reason = values.pop("submitted_reason")
    values.update(extra_fields)
    values.update(
        {
            "external_id": f"MANUAL:{manual_id}",
            "source_record_id": f"MANUAL:{manual_id}",
            "manual_source_reference": source_reference,
            "manual_submission_reason": submitted_reason,
            "manual_entry_id": manual_id,
        }
    )
    return services.ingest_batch(
        db,
        amo_id=amo_id,
        source=sources["MANUAL-ENTRY"],
        payload=schemas.ReliabilityBatchIngest(
            records=[values],
            metadata_json={
                "adapter": "manual-v1",
                "submission_channel": "reliability-ui",
                "actor_user_id": actor_user_id,
                "submitted_reason": submitted_reason,
            },
        ),
        actor_user_id=actor_user_id,
    )


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def internal_source_coverage(db: Session, *, amo_id: str) -> InternalSourceCoverage:
    source_map = {
        item.code: item
        for item in db.query(domain.ReliabilitySource).filter(domain.ReliabilitySource.amo_id == amo_id).all()
    }
    workpack_count, workpack_latest = db.query(
        func.count(work_models.TaskCard.id), func.max(work_models.TaskCard.updated_at)
    ).filter(
        work_models.TaskCard.amo_id == amo_id,
        or_(
            work_models.TaskCard.category.in_([work_models.TaskCategoryEnum.DEFECT, work_models.TaskCategoryEnum.UNSCHEDULED]),
            work_models.TaskCard.origin_type == work_models.TaskOriginTypeEnum.NON_ROUTINE,
        ),
    ).one()
    removal_count, removal_latest = db.query(
        func.count(legacy.RemovalEvent.id), func.max(legacy.RemovalEvent.removed_at)
    ).filter(legacy.RemovalEvent.amo_id == amo_id).one()
    usage_count, usage_latest = _usage_latest(db, amo_id=amo_id)
    ehm_count, ehm_latest = db.query(
        func.count(legacy.EngineTrendStatus.id), func.max(legacy.EngineTrendStatus.updated_at)
    ).filter(legacy.EngineTrendStatus.amo_id == amo_id).one()
    manual_source = source_map.get("MANUAL-ENTRY")
    manual_count = 0
    manual_latest = None
    if manual_source:
        manual_count, manual_latest = db.query(
            func.count(domain.ReliabilityIngestionRecord.id),
            func.max(domain.ReliabilityIngestionRecord.created_at),
        ).filter(
            domain.ReliabilityIngestionRecord.amo_id == amo_id,
            domain.ReliabilityIngestionRecord.source_id == manual_source.id,
        ).one()

    stats = {
        "WORKPACK-TASKS": (int(workpack_count or 0), workpack_latest),
        "COMPONENT-REMOVALS": (int(removal_count or 0), removal_latest),
        "TECH-RECORDS-USAGE": (int(usage_count or 0), usage_latest),
        "EHM-INTERNAL": (int(ehm_count or 0), ehm_latest),
        "MANUAL-ENTRY": (int(manual_count or 0), manual_latest),
    }
    items: List[InternalSourceCoverageItem] = []
    for spec in INTERNAL_SOURCE_SPECS:
        source = source_map.get(spec.code)
        count, latest = stats[spec.code]
        if not source:
            integration_status = "CONFIGURATION_REQUIRED"
            detail = "Reserved source has not been configured. Run Configure sources."
        elif count == 0:
            integration_status = "NO_DATA"
            detail = "Adapter is configured, but the authoritative module has no qualifying records."
        elif spec.transport == "INTERNAL" and not source.last_success_at:
            integration_status = "SYNC_REQUIRED"
            detail = "Authoritative records exist but have not yet been harvested into Reliability."
        else:
            integration_status = "WIRED"
            detail = "Authoritative records are linked through the canonical Reliability ingestion path."
        items.append(
            InternalSourceCoverageItem(
                code=spec.code,
                module=spec.module,
                dataset=spec.dataset,
                source_id=source.id if source else None,
                source_status=source.status if source else "MISSING",
                integration_status=integration_status,
                record_count=count,
                latest_record_at=_iso(latest),
                last_sync_at=source.last_success_at if source else None,
                manual_fallback=spec.manual_fallback,
                detail=detail,
            )
        )
    return InternalSourceCoverage(generated_at=datetime.now(timezone.utc), items=items)


def _context(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
) -> tuple[account_models.User, Session, str]:
    return current_user, db, services.tenant_id(current_user)


def manual_entry_route(payload: ManualReliabilityEntry, context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ingest")
    return create_manual_entry(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


def configure_internal_sources_route(context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.source.manage")
    ensure_reserved_sources(db, amo_id=amo_id, actor_user_id=str(current_user.id))
    return internal_source_coverage(db, amo_id=amo_id)


def internal_source_coverage_route(context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.read")
    return internal_source_coverage(db, amo_id=amo_id)


def register(router: APIRouter) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    services.harvest_internal_sources = harvest_internal_sources
    services.bootstrap_reliability = bootstrap_reliability
    router.add_api_route(
        "/manual-entry",
        manual_entry_route,
        methods=["POST"],
        response_model=schemas.ReliabilityIngestionResult,
        status_code=status.HTTP_201_CREATED,
        summary="Create a controlled manual Reliability occurrence",
    )
    router.add_api_route(
        "/internal-sources/configure",
        configure_internal_sources_route,
        methods=["POST"],
        response_model=InternalSourceCoverage,
        summary="Configure reserved internal Reliability sources",
    )
    router.add_api_route(
        "/internal-sources/coverage",
        internal_source_coverage_route,
        methods=["GET"],
        response_model=InternalSourceCoverage,
        summary="Show Reliability source wiring and authoritative data coverage",
    )
    _REGISTERED = True
'''


TESTS = r'''from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from amodb.apps.reliability import workpack_integration as integration
from amodb.apps.work import models as work_models


def test_reserved_sources_cover_authoritative_workpack_domains():
    codes = {item.code for item in integration.INTERNAL_SOURCE_SPECS}
    assert {
        "WORKPACK-TASKS",
        "COMPONENT-REMOVALS",
        "TECH-RECORDS-USAGE",
        "EHM-INTERNAL",
        "MANUAL-ENTRY",
    }.issubset(codes)
    assert all(item.manual_fallback for item in integration.INTERNAL_SOURCE_SPECS)


def test_manual_entry_rejects_unknown_event_type():
    with pytest.raises(ValidationError):
        integration.ManualReliabilityEntry(
            event_type="NOT_A_REAL_EVENT",
            occurred_at=datetime.now(timezone.utc),
            description="Test entry",
            submitted_reason="Controlled manual capture",
        )


def test_workpack_task_record_retains_source_links_and_revision_identity():
    now = datetime.now(timezone.utc)
    work_order = SimpleNamespace(
        wo_number="WO-100",
        work_package_ref="PACK-77",
        check_type="A-CHECK",
        operator_event_id=None,
        status=work_models.WorkOrderStatusEnum.IN_PROGRESS,
    )
    task = SimpleNamespace(
        id=55,
        work_order=work_order,
        work_order_id=12,
        aircraft_serial_number="AC-001",
        aircraft_component_id=8,
        ata_chapter="32",
        task_code="NR-55",
        operator_event_id=None,
        priority=work_models.TaskPriorityEnum.HIGH,
        title="Repeat landing gear indication",
        description="Repeat defect found during the workpack.",
        component=SimpleNamespace(part_number="PN-1", serial_number="SN-1"),
        actual_end=now,
        actual_start=None,
        updated_at=now,
        created_at=now,
        category=work_models.TaskCategoryEnum.DEFECT,
        origin_type=work_models.TaskOriginTypeEnum.NON_ROUTINE,
        status=work_models.TaskStatusEnum.IN_PROGRESS,
        parent_task_id=None,
        program_item_id=4,
    )
    record = integration._task_record(task)
    assert record["event_type"] == "REPEAT_DEFECT"
    assert record["work_order_id"] == 12
    assert record["task_card_id"] == 55
    assert record["work_package_ref"] == "PACK-77"
    assert record["part_number"] == "PN-1"
    assert record["external_id"].startswith("WORKPACK_TASK:55:")


def test_router_registers_manual_and_coverage_contracts():
    from amodb.apps.reliability.router import router

    paths = {route.path for route in router.routes}
    assert "/reliability/manual-entry" in paths
    assert "/reliability/internal-sources/configure" in paths
    assert "/reliability/internal-sources/coverage" in paths
'''


DOC = r'''# Reliability Workpack and Internal Data Wiring

## Purpose

Reliability must consume authoritative operational records from the modules that create them. It must not create parallel editable copies of work orders, task cards, utilisation, component movements or EHM records.

## Reserved sources

| Source code | Authoritative module | Records consumed | Reliability use |
|---|---|---|---|
| `WORKPACK-TASKS` | Work Orders / Workpack | Defect and non-routine task cards | Defect, repeat-defect and ATA analysis |
| `COMPONENT-REMOVALS` | Components / Stores / Workpack | Removal events, part movements and serialized component identity | Scheduled and unscheduled removal analysis |
| `TECH-RECORDS-USAGE` | Technical Records / Fleet | Aircraft daily flight hours and cycles | Exposure denominators |
| `EHM-INTERNAL` | Engine Health Monitoring | Engine trend shifts | Engine-health Reliability occurrences |
| `MANUAL-ENTRY` | Reliability | Structured human-entered records | Controlled fallback when an upstream module is unavailable |

## Rules

1. Internal sync uses source IDs and immutable ingestion batches.
2. Workpack events retain work order, work-package reference, task card, maintenance-program item, component and ATA references.
3. Updated task cards create a new source revision identity rather than overwriting the prior Reliability event.
4. Aircraft utilisation remains authoritative in Technical Records/Fleet and is read directly by the calculation engine.
5. Manual entry uses the same validation, provenance, data-quality and audit path as automated ingestion.
6. Manual entries require an accountable reason and may be linked to an existing work order or task card.
7. Source coverage exposes missing configuration, no-data, sync-required and wired states.

## Initial scope

This implementation wires the datasets already present in the portal. Flight-operations interruptions, MEL/CDL, shop findings, QMS and SMS require their own authoritative upstream records or integration adapters; until then, controlled manual entry is available and remains visibly identified as manual evidence.
'''


write("backend/amodb/apps/reliability/workpack_integration.py", WORKPACK_INTEGRATION)
write("backend/amodb/apps/reliability/tests/test_workpack_integration.py", TESTS)
write("docs/reliability/WORKPACK_DATA_WIRING.md", DOC)

init_path = ROOT / "backend/amodb/apps/reliability/__init__.py"
init_text = init_path.read_text(encoding="utf-8")
init_text = replace_once(
    init_text,
    "from . import advanced_models  # noqa: E402,F401\n",
    "from . import advanced_models  # noqa: E402,F401\nfrom . import workpack_integration  # noqa: E402,F401\n\nworkpack_integration.register(router)\n",
    label="reliability package registration",
)
init_path.write_text(init_text, encoding="utf-8")

service_path = ROOT / "frontend/src/services/reliability.ts"
service_text = service_path.read_text(encoding="utf-8")
service_text = replace_once(
    service_text,
    "export type ReliabilityIngestionResult = {\n  batch: ReliabilityIngestionBatch; created_event_ids: number[];\n  duplicate_external_ids: string[]; rejected_records: Array<Record<string, unknown>>;\n};\n",
    "export type ReliabilityIngestionResult = {\n  batch: ReliabilityIngestionBatch; created_event_ids: number[];\n  duplicate_external_ids: string[]; rejected_records: Array<Record<string, unknown>>;\n};\nexport type ReliabilityInternalSourceCoverageItem = {\n  code: string; module: string; dataset: string; source_id?: string | null;\n  source_status: string; integration_status: string; record_count: number;\n  latest_record_at?: string | null; last_sync_at?: string | null;\n  manual_fallback: boolean; detail: string;\n};\nexport type ReliabilityInternalSourceCoverage = {\n  generated_at: string; items: ReliabilityInternalSourceCoverageItem[];\n};\nexport type ManualReliabilityEntryPayload = {\n  event_type: string; occurred_at: string; description: string; submitted_reason: string;\n  source_reference?: string | null; severity?: string; aircraft_serial_number?: string | null;\n  work_order_id?: number | null; task_card_id?: number | null; component_id?: number | null;\n  ata_chapter?: string | null; reference_code?: string | null; engine_position?: string | null;\n  flight_number?: string | null; origin_station?: string | null; destination_station?: string | null;\n  delay_minutes?: number | null; mel_reference?: string | null; cdl_reference?: string | null;\n  deferral_expires_at?: string | null; part_number?: string | null;\n  component_serial_number?: string | null; confirmed_failure?: boolean | null;\n  repeat_key?: string | null; extra_fields?: Record<string, unknown>;\n};\n",
    label="reliability client coverage types",
)
service_text = replace_once(
    service_text,
    "export const harvestInternalReliabilitySources = (): Promise<ReliabilityIngestionResult[]> =>\n  reliabilityMutation(\"/reliability/sources/harvest-internal\", \"POST\");\n",
    "export const harvestInternalReliabilitySources = (): Promise<ReliabilityIngestionResult[]> =>\n  reliabilityMutation(\"/reliability/sources/harvest-internal\", \"POST\");\nexport const configureReliabilityInternalSources = (): Promise<ReliabilityInternalSourceCoverage> =>\n  reliabilityMutation(\"/reliability/internal-sources/configure\", \"POST\");\nexport const getReliabilityInternalSourceCoverage = (): Promise<ReliabilityInternalSourceCoverage> =>\n  apiRequest(\"/reliability/internal-sources/coverage\", { cacheTtlMs: 10_000 });\nexport const createManualReliabilityEntry = (payload: ManualReliabilityEntryPayload): Promise<ReliabilityIngestionResult> =>\n  reliabilityMutation(\"/reliability/manual-entry\", \"POST\", payload);\n",
    label="reliability client integration functions",
)
service_path.write_text(service_text, encoding="utf-8")

view_path = ROOT / "frontend/src/pages/reliability/ReliabilityAdvancedViews.tsx"
view_text = view_path.read_text(encoding="utf-8")
view_text = replace_once(
    view_text,
    "  createReliabilityChange,\n",
    "  createManualReliabilityEntry,\n  createReliabilityChange,\n",
    label="manual entry import",
)
view_text = replace_once(
    view_text,
    "  createReliabilityThresholdVersion,\n",
    "  createReliabilityThresholdVersion,\n  configureReliabilityInternalSources,\n",
    label="configure source import",
)
view_text = replace_once(
    view_text,
    "  getReliabilityCompliance,\n",
    "  getReliabilityCompliance,\n  getReliabilityInternalSourceCoverage,\n",
    label="coverage function import",
)
view_text = replace_once(
    view_text,
    "  type ReliabilityIngestionBatch,\n",
    "  type ReliabilityIngestionBatch,\n  type ReliabilityInternalSourceCoverage,\n",
    label="coverage type import",
)

start = view_text.index("function SourcesView()")
end = view_text.index("\nfunction DataQualityView()", start)
segment = view_text[start:end]
segment = replace_once(
    segment,
    "  const batches = useResource<ReliabilityIngestionBatch[]>(() => listReliabilityIngestionBatches(), []);\n",
    "  const batches = useResource<ReliabilityIngestionBatch[]>(() => listReliabilityIngestionBatches(), []);\n  const coverage = useResource<ReliabilityInternalSourceCoverage>(() => getReliabilityInternalSourceCoverage(), []);\n",
    label="coverage resource",
)
segment = replace_once(
    segment,
    "      batches.refresh();\n",
    "      batches.refresh();\n      coverage.refresh();\n",
    label="coverage refresh",
)
segment = replace_once(
    segment,
    "  return (\n",
    '''  const submitManual = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const numberOrNull = (name: string): number | null => {
      const raw = String(data.get(name) || "").trim();
      return raw ? Number(raw) : null;
    };
    void runAction(() => createManualReliabilityEntry({
      event_type: String(data.get("event_type") || "DEFECT"),
      occurred_at: new Date(String(data.get("occurred_at") || new Date().toISOString())).toISOString(),
      description: String(data.get("description") || ""),
      submitted_reason: String(data.get("submitted_reason") || ""),
      source_reference: String(data.get("source_reference") || "") || null,
      severity: String(data.get("severity") || "MEDIUM"),
      aircraft_serial_number: String(data.get("aircraft_serial_number") || "") || null,
      work_order_id: numberOrNull("work_order_id"),
      task_card_id: numberOrNull("task_card_id"),
      component_id: numberOrNull("component_id"),
      ata_chapter: String(data.get("ata_chapter") || "") || null,
      reference_code: String(data.get("reference_code") || "") || null,
      engine_position: String(data.get("engine_position") || "") || null,
      flight_number: String(data.get("flight_number") || "") || null,
      origin_station: String(data.get("origin_station") || "") || null,
      destination_station: String(data.get("destination_station") || "") || null,
      delay_minutes: numberOrNull("delay_minutes"),
      mel_reference: String(data.get("mel_reference") || "") || null,
      cdl_reference: String(data.get("cdl_reference") || "") || null,
      part_number: String(data.get("part_number") || "") || null,
      component_serial_number: String(data.get("component_serial_number") || "") || null,
      confirmed_failure: data.get("confirmed_failure") === "true" ? true : data.get("confirmed_failure") === "false" ? false : null,
    }));
  };

  return (
''',
    label="manual submit handler",
)
segment = replace_once(
    segment,
    '          actions={<button className="btn btn-secondary" type="button" disabled={!hasCapability(capabilities, "reliability.ingest")} onClick={() => void runAction(() => harvestInternalReliabilitySources())}>Harvest internal sources</button>}\n',
    '''          actions={<><button className="btn btn-secondary" type="button" disabled={!hasCapability(capabilities, "reliability.source.manage")} onClick={() => void runAction(() => configureReliabilityInternalSources())}>Configure sources</button><button className="btn btn-primary" type="button" disabled={!hasCapability(capabilities, "reliability.ingest")} onClick={() => void runAction(() => harvestInternalReliabilitySources())}>Sync workpack data</button></>}
''',
    label="source actions",
)
segment = replace_once(
    segment,
    "        <RequestState loading={sources.loading || batches.loading} error={sources.error || batches.error || actionError} />\n",
    "        <RequestState loading={sources.loading || batches.loading || coverage.loading} error={sources.error || batches.error || coverage.error || actionError} />\n",
    label="coverage request state",
)
manual_section = '''      <section className="reliability-v2__section">
        <PageHeading eyebrow="Controlled fallback" title="Manual Reliability entry" detail="Use this only when the authoritative upstream module cannot provide the record. Work-order and task-card links are validated against the current tenant and the entry retains its manual justification." />
        <form className="reliability-v2__form" onSubmit={submitManual}>
          <div className="reliability-v2__form-grid">
            <label>Occurrence type<select name="event_type" defaultValue="DEFECT">{EVENT_TYPES.map((eventType) => <option key={eventType}>{eventType}</option>)}</select></label>
            <label>Occurred at<input name="occurred_at" type="datetime-local" defaultValue={localDateTime()} required /></label>
            <label>Severity<select name="severity" defaultValue="MEDIUM"><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
            <label>Aircraft serial<input name="aircraft_serial_number" placeholder="Filled from task/work order when linked" /></label>
            <label>Work order ID<input name="work_order_id" type="number" min="1" /></label>
            <label>Task card ID<input name="task_card_id" type="number" min="1" /></label>
            <label>Component ID<input name="component_id" type="number" min="1" /></label>
            <label>ATA chapter<input name="ata_chapter" placeholder="32" /></label>
            <label>Reference<input name="reference_code" placeholder="Tech log / card / report reference" /></label>
            <label>Source reference<input name="source_reference" placeholder="External document or verbal report reference" /></label>
            <label>Flight number<input name="flight_number" /></label>
            <label>Delay minutes<input name="delay_minutes" type="number" min="0" /></label>
            <label>Origin<input name="origin_station" maxLength={8} /></label>
            <label>Destination<input name="destination_station" maxLength={8} /></label>
            <label>Engine position<input name="engine_position" /></label>
            <label>Part number<input name="part_number" /></label>
            <label>Component serial<input name="component_serial_number" /></label>
            <label>Confirmed failure<select name="confirmed_failure" defaultValue=""><option value="">Not determined</option><option value="true">Yes</option><option value="false">No / NFF</option></select></label>
            <label>MEL reference<input name="mel_reference" /></label>
            <label>CDL reference<input name="cdl_reference" /></label>
          </div>
          <label>Description<textarea name="description" rows={4} required /></label>
          <label>Why manual entry is required<textarea name="submitted_reason" rows={3} required placeholder="State why the upstream module or source record was unavailable and who supplied the evidence." /></label>
          <button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.ingest")}>Validate and record occurrence</button>
          <PermissionNote capability="reliability.ingest" snapshot={capabilities} />
        </form>
      </section>
      <section className="reliability-v2__section">
        <PageHeading eyebrow="Integration coverage" title="Authoritative module wiring" detail="This shows whether each required upstream dataset is configured, contains records and has been synchronised. Manual fallback does not make a missing upstream feed healthy." />
        <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Source</th><th>Module</th><th>Dataset</th><th>Coverage</th><th>Records</th><th>Latest record</th><th>Last sync</th><th>Detail</th></tr></thead><tbody>
          {(coverage.data?.items || []).map((item) => <tr key={item.code}><td><strong>{item.code}</strong><small>{item.source_status}</small></td><td>{item.module}</td><td>{item.dataset}</td><td><span className={statusClass(item.integration_status)}>{item.integration_status.replaceAll("_", " ")}</span></td><td>{item.record_count}</td><td>{displayDate(item.latest_record_at)}</td><td>{displayDate(item.last_sync_at)}</td><td>{item.detail}</td></tr>)}
          {!coverage.data?.items.length && <tr><td colSpan={8}>Source coverage has not been evaluated.</td></tr>}
        </tbody></table></div>
      </section>
'''
segment = replace_once(
    segment,
    '      <section className="reliability-v2__section">\n        <PageHeading eyebrow="Source health"',
    manual_section + '      <section className="reliability-v2__section">\n        <PageHeading eyebrow="Source health"',
    label="manual and coverage sections",
)
view_text = view_text[:start] + segment + view_text[end:]
view_path.write_text(view_text, encoding="utf-8")

# Remove the one-shot patch machinery from the resulting commit.
(ROOT / "scripts/apply_reliability_workpack_wiring.py").unlink(missing_ok=True)
(ROOT / ".github/workflows/reliability-workpack-wiring.yml").unlink(missing_ok=True)
