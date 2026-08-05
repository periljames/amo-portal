from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.work import models as work_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from . import advanced_models as domain
from . import advanced_schemas as schemas
from . import advanced_services as services
from . import models as legacy
from . import workpack_integration as workpack


class AuthoritativeAdapterSpec(BaseModel):
    code: str
    name: str
    source_type: schemas.ReliabilitySourceType
    module: str
    dataset: str
    connection_mode: Literal["INTERNAL_LINK", "AUTHORITATIVE_PUSH", "HISTORICAL_IMPORT"]
    authoritative_tables: List[str] = Field(default_factory=list)
    implementation_state: Literal["READY", "UPSTREAM_REQUIRED", "MAPPING_REQUIRED"]
    detail: str


ADAPTER_SPECS: tuple[AuthoritativeAdapterSpec, ...] = (
    AuthoritativeAdapterSpec(
        code="FLIGHT-OPERATIONS",
        name="Flight Operations technical interruptions",
        source_type="FLIGHT_OPERATIONS",
        module="Flight Operations",
        dataset="Technical delays, cancellations, return-to-gate events, turnbacks and diversions",
        connection_mode="AUTHORITATIVE_PUSH",
        implementation_state="UPSTREAM_REQUIRED",
        detail="The canonical adapter contract is available, but this repository has no Flight Operations source-of-record module.",
    ),
    AuthoritativeAdapterSpec(
        code="MEL-CDL",
        name="MEL and CDL deferrals",
        source_type="MEL_CDL",
        module="Technical Operations / Defect Control",
        dataset="Controlled MEL/CDL deferrals, expiry and revision events",
        connection_mode="AUTHORITATIVE_PUSH",
        implementation_state="UPSTREAM_REQUIRED",
        detail="The canonical adapter contract is available, but this repository has no authoritative MEL/CDL deferral register.",
    ),
    AuthoritativeAdapterSpec(
        code="COMPONENT-SHOP-FINDINGS",
        name="Component shop findings and NFF dispositions",
        source_type="COMPONENT_SHOP",
        module="Component Shop",
        dataset="Shop findings, confirmed failures and no-fault-found dispositions",
        connection_mode="AUTHORITATIVE_PUSH",
        implementation_state="UPSTREAM_REQUIRED",
        detail="Removal evidence exists, but an authoritative component-shop report and disposition source is not present.",
    ),
    AuthoritativeAdapterSpec(
        code="QMS-FINDING-LINKS",
        name="QMS finding links",
        source_type="QMS",
        module="Quality Management System",
        dataset="Explicitly linked audit findings and objective evidence",
        connection_mode="INTERNAL_LINK",
        authoritative_tables=["qms_audits", "qms_audit_findings"],
        implementation_state="READY",
        detail="QMS findings can be linked through a tenant-validated, reason-controlled Reliability occurrence route.",
    ),
    AuthoritativeAdapterSpec(
        code="SMS-EVENTS",
        name="SMS safety occurrence links",
        source_type="SMS",
        module="Safety Management System",
        dataset="Safety occurrences selected for Reliability analysis",
        connection_mode="AUTHORITATIVE_PUSH",
        implementation_state="UPSTREAM_REQUIRED",
        detail="The canonical adapter contract is available, but this repository has no authoritative SMS occurrence module.",
    ),
    AuthoritativeAdapterSpec(
        code="WORKBOOK-HISTORY",
        name="Historical workbook reconciliation",
        source_type="MANUAL",
        module="Reliability Data Migration",
        dataset="Mapped historical workbook occurrences with row-level provenance",
        connection_mode="HISTORICAL_IMPORT",
        implementation_state="MAPPING_REQUIRED",
        detail="A controlled row contract is available; tenant-specific workbook mapping and reconciliation approval remain required.",
    ),
)


_ALLOWED_SEVERITIES = {item.value for item in legacy.ReliabilitySeverityEnum}
_ALLOWED_EVENT_TYPES = {item.value for item in legacy.ReliabilityEventTypeEnum}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _revisioned_external_id(code: str, source_record_id: str, source_revision: str) -> str:
    record = source_record_id.strip()
    revision = source_revision.strip()
    if not record or not revision:
        raise ValueError("Source record ID and revision are required.")
    return f"{code}:{record}:{revision}"[:255]


def _normalise_station(value: Optional[str]) -> Optional[str]:
    return value.strip().upper() if value else None


def _normalise_severity(value: str) -> str:
    resolved = value.strip().upper()
    if resolved not in _ALLOWED_SEVERITIES:
        raise ValueError("Unsupported Reliability severity.")
    return resolved


class AuthoritativeRecordBase(BaseModel):
    source_record_id: str = Field(min_length=1, max_length=160)
    source_revision: str = Field(min_length=1, max_length=64)
    occurred_at: datetime
    aircraft_serial_number: Optional[str] = Field(default=None, max_length=50)
    description: str = Field(min_length=3, max_length=12000)
    severity: str = "MEDIUM"
    ata_chapter: Optional[str] = Field(default=None, max_length=20)
    reference_code: Optional[str] = Field(default=None, max_length=64)
    extra_fields: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        return _normalise_severity(value)


FlightInterruptionType = Literal[
    "TECHNICAL_DELAY",
    "TECHNICAL_CANCELLATION",
    "RETURN_TO_GATE",
    "AIR_TURNBACK",
    "DIVERSION",
    "IN_FLIGHT_SHUTDOWN",
    "ABORTED_TAKEOFF",
]


class FlightOperationsOccurrence(AuthoritativeRecordBase):
    event_type: FlightInterruptionType
    flight_number: str = Field(min_length=1, max_length=24)
    origin_station: Optional[str] = Field(default=None, max_length=8)
    destination_station: Optional[str] = Field(default=None, max_length=8)
    scheduled_departure_at: Optional[datetime] = None
    actual_departure_at: Optional[datetime] = None
    delay_minutes: Optional[int] = Field(default=None, ge=0, le=2147483647)
    dispatch_impact: Optional[str] = Field(default=None, max_length=40)

    @field_validator("origin_station", "destination_station")
    @classmethod
    def normalise_station(cls, value: Optional[str]) -> Optional[str]:
        return _normalise_station(value)

    @model_validator(mode="after")
    def validate_operational_impact(self):
        if self.event_type == "TECHNICAL_DELAY" and self.delay_minutes is None:
            raise ValueError("Technical delay records require delay_minutes.")
        return self


DeferralType = Literal["MEL_DEFERRAL", "CDL_DEFERRAL"]


class DeferralOccurrence(AuthoritativeRecordBase):
    event_type: DeferralType
    mel_reference: Optional[str] = Field(default=None, max_length=80)
    cdl_reference: Optional[str] = Field(default=None, max_length=80)
    deferral_category: Optional[str] = Field(default=None, max_length=16)
    deferred_until: datetime
    control_basis: str = Field(min_length=3, max_length=2000)
    flight_number: Optional[str] = Field(default=None, max_length=24)

    @model_validator(mode="after")
    def validate_deferral(self):
        if self.event_type == "MEL_DEFERRAL" and not self.mel_reference:
            raise ValueError("MEL deferrals require mel_reference.")
        if self.event_type == "CDL_DEFERRAL" and not self.cdl_reference:
            raise ValueError("CDL deferrals require cdl_reference.")
        if _utc(self.deferred_until) < _utc(self.occurred_at):
            raise ValueError("Deferral expiry cannot precede the occurrence time.")
        return self


ShopEventType = Literal["SHOP_FINDING", "NO_FAULT_FOUND"]


class ComponentShopOccurrence(AuthoritativeRecordBase):
    event_type: ShopEventType
    part_number: str = Field(min_length=1, max_length=80)
    component_serial_number: str = Field(min_length=1, max_length=80)
    component_id: Optional[int] = Field(default=None, ge=1)
    shop_order_reference: str = Field(min_length=1, max_length=120)
    confirmed_failure: Optional[bool] = None
    disposition: str = Field(min_length=2, max_length=2000)

    @model_validator(mode="after")
    def validate_disposition(self):
        if self.event_type == "NO_FAULT_FOUND" and self.confirmed_failure is not False:
            raise ValueError("NO_FAULT_FOUND records must explicitly set confirmed_failure to false.")
        return self


class SmsOccurrence(AuthoritativeRecordBase):
    event_type: Literal["SAFETY_EVENT"] = "SAFETY_EVENT"
    sms_reference: str = Field(min_length=1, max_length=120)
    risk_classification: str = Field(min_length=1, max_length=80)
    reliability_link_reason: str = Field(min_length=5, max_length=2000)


class HistoricalOccurrence(AuthoritativeRecordBase):
    event_type: str
    source_workbook: str = Field(min_length=1, max_length=255)
    source_sheet: str = Field(min_length=1, max_length=255)
    source_row_number: int = Field(ge=1)
    mapping_profile: str = Field(min_length=1, max_length=120)
    reconciliation_status: Literal["MAPPED", "REVIEWED", "APPROVED"]
    reconciliation_note: str = Field(min_length=3, max_length=4000)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        resolved = services.EVENT_ALIASES.get(value.strip().upper(), value.strip().upper())
        if resolved not in _ALLOWED_EVENT_TYPES:
            raise ValueError("Unsupported Reliability event type.")
        return resolved


class QmsFindingLinkRequest(BaseModel):
    event_type: Literal["MAINTENANCE_ERROR", "SUPPLIER_ESCAPE", "SAFETY_EVENT", "OTHER"]
    reliability_link_reason: str = Field(min_length=5, max_length=4000)
    aircraft_serial_number: Optional[str] = Field(default=None, max_length=50)
    ata_chapter: Optional[str] = Field(default=None, max_length=20)
    severity: Optional[str] = None

    @field_validator("severity")
    @classmethod
    def validate_optional_severity(cls, value: Optional[str]) -> Optional[str]:
        return _normalise_severity(value) if value else None


class AdapterReadinessItem(BaseModel):
    code: str
    module: str
    dataset: str
    implementation_state: str
    connection_state: str
    source_id: Optional[str] = None
    available_record_count: int = 0
    ingested_record_count: int = 0
    latest_available_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    detail: str


class AdapterReadinessResponse(BaseModel):
    generated_at: datetime
    items: List[AdapterReadinessItem]


class AdapterSyncResponse(BaseModel):
    results: List[schemas.ReliabilityIngestionResult] = Field(default_factory=list)
    readiness: AdapterReadinessResponse


def _configuration(spec: AuthoritativeAdapterSpec) -> Dict[str, Any]:
    return {
        "adapter": "authoritative-adapter-v1",
        "module": spec.module,
        "dataset": spec.dataset,
        "connection_mode": spec.connection_mode,
        "authoritative_tables": spec.authoritative_tables,
        "canonical_contract": "reliability-event-v1",
        "implementation_state": spec.implementation_state,
        "reserved_source": True,
    }


def _ensure_source(
    db: Session,
    *,
    amo_id: str,
    spec: AuthoritativeAdapterSpec,
    actor_user_id: str,
) -> domain.ReliabilitySource:
    source = (
        db.query(domain.ReliabilitySource)
        .filter(domain.ReliabilitySource.amo_id == amo_id, domain.ReliabilitySource.code == spec.code)
        .first()
    )
    expected_transport = "INTERNAL" if spec.connection_mode == "INTERNAL_LINK" else "PUSH"
    if source:
        changed = False
        expected = {
            "name": spec.name,
            "source_type": spec.source_type,
            "transport": expected_transport,
            "mapping_version": "authoritative-adapter-v1",
            "status": "ACTIVE",
        }
        for field_name, value in expected.items():
            if getattr(source, field_name) != value:
                setattr(source, field_name, value)
                changed = True
        configuration = {**(source.configuration_json or {}), **_configuration(spec)}
        if configuration != (source.configuration_json or {}):
            source.configuration_json = configuration
            changed = True
        if changed:
            services.append_audit(
                db,
                amo_id=amo_id,
                entity_type="SOURCE",
                entity_id=source.id,
                action="AUTHORITATIVE_ADAPTER_CONFIGURED",
                payload={"code": spec.code, "implementation_state": spec.implementation_state},
                actor_user_id=actor_user_id,
            )
            db.commit()
            db.refresh(source)
        return source
    return services.create_source(
        db,
        amo_id=amo_id,
        payload=schemas.ReliabilitySourceCreate(
            code=spec.code,
            name=spec.name,
            source_type=spec.source_type,
            transport=expected_transport,
            mapping_version="authoritative-adapter-v1",
            configuration_json=_configuration(spec),
            poll_interval_minutes=60 if expected_transport == "INTERNAL" else None,
        ),
        actor_user_id=actor_user_id,
    )


def ensure_adapter_sources(db: Session, *, amo_id: str, actor_user_id: str) -> Dict[str, domain.ReliabilitySource]:
    return {
        spec.code: _ensure_source(db, amo_id=amo_id, spec=spec, actor_user_id=actor_user_id)
        for spec in ADAPTER_SPECS
    }


def _assert_aircraft(db: Session, *, amo_id: str, aircraft_serial_number: Optional[str]) -> None:
    if not aircraft_serial_number:
        return
    exists = (
        db.query(fleet_models.Aircraft.serial_number)
        .filter(
            fleet_models.Aircraft.amo_id == amo_id,
            fleet_models.Aircraft.serial_number == aircraft_serial_number,
        )
        .first()
    )
    if not exists:
        raise HTTPException(status_code=422, detail="The referenced aircraft does not exist in this tenant.")


def _assert_component(
    db: Session,
    *,
    amo_id: str,
    component_id: Optional[int],
    part_number: str,
    serial_number: str,
    aircraft_serial_number: Optional[str],
) -> None:
    if not component_id:
        return
    component = (
        db.query(fleet_models.AircraftComponent)
        .filter(
            fleet_models.AircraftComponent.amo_id == amo_id,
            fleet_models.AircraftComponent.id == component_id,
        )
        .first()
    )
    if not component:
        raise HTTPException(status_code=422, detail="The referenced component does not exist in this tenant.")
    conflicts = []
    if component.part_number and component.part_number != part_number:
        conflicts.append("part number")
    if component.serial_number and component.serial_number != serial_number:
        conflicts.append("serial number")
    if aircraft_serial_number and component.aircraft_serial_number != aircraft_serial_number:
        conflicts.append("aircraft")
    if conflicts:
        raise HTTPException(status_code=422, detail=f"Component {'/'.join(conflicts)} conflicts with the authoritative component record.")


def _record_payload(code: str, payload: AuthoritativeRecordBase) -> Dict[str, Any]:
    values = payload.model_dump(mode="json")
    extra_fields = dict(values.pop("extra_fields", {}) or {})
    source_record_id = values.pop("source_record_id")
    source_revision = values.pop("source_revision")
    values.update(extra_fields)
    values.update(
        {
            "external_id": _revisioned_external_id(code, source_record_id, source_revision),
            "authoritative_source_record_id": source_record_id,
            "authoritative_source_revision": source_revision,
        }
    )
    return values


def _ingest_records(
    db: Session,
    *,
    amo_id: str,
    code: str,
    payloads: List[AuthoritativeRecordBase],
    actor_user_id: str,
) -> schemas.ReliabilityIngestionResult:
    spec = next(item for item in ADAPTER_SPECS if item.code == code)
    source = _ensure_source(db, amo_id=amo_id, spec=spec, actor_user_id=actor_user_id)
    records: List[Dict[str, Any]] = []
    for payload in payloads:
        _assert_aircraft(db, amo_id=amo_id, aircraft_serial_number=payload.aircraft_serial_number)
        if isinstance(payload, ComponentShopOccurrence):
            _assert_component(
                db,
                amo_id=amo_id,
                component_id=payload.component_id,
                part_number=payload.part_number,
                serial_number=payload.component_serial_number,
                aircraft_serial_number=payload.aircraft_serial_number,
            )
        records.append(_record_payload(code, payload))
    return services.ingest_batch(
        db,
        amo_id=amo_id,
        source=source,
        payload=schemas.ReliabilityBatchIngest(
            records=records,
            metadata_json={
                "adapter": "authoritative-adapter-v1",
                "source_code": code,
                "record_count": len(records),
            },
        ),
        actor_user_id=actor_user_id,
    )


def _scheduled_check_context(task: work_models.TaskCard, record: Dict[str, Any]) -> Dict[str, Any]:
    origin = str(getattr(getattr(task, "origin_type", None), "value", getattr(task, "origin_type", "")))
    work_order = getattr(task, "work_order", None)
    if origin != "NON_ROUTINE" or not work_order or not bool(getattr(work_order, "is_scheduled", False)):
        return record
    updated = dict(record)
    updated["external_id"] = f"{record['external_id']}:SCHEDULED_CHECK_V2"[:255]
    updated["scheduled_check_finding"] = True
    updated["maintenance_finding_context"] = "SCHEDULED_CHECK"
    updated["source_mapping_revision"] = "scheduled-check-v2"
    updated["parent_scheduled_task_id"] = getattr(task, "parent_task_id", None)
    return updated


def _install_workpack_decorator() -> None:
    current = workpack._task_record
    if getattr(current, "_scheduled_check_decorator", False):
        return

    def decorated(task: work_models.TaskCard) -> Dict[str, Any]:
        return _scheduled_check_context(task, current(task))

    setattr(decorated, "_scheduled_check_decorator", True)
    workpack._task_record = decorated


def _qms_severity(value: Any, *, safety_sensitive: bool) -> str:
    if safety_sensitive:
        return "CRITICAL"
    resolved = str(getattr(value, "value", value) or "").upper()
    if any(token in resolved for token in ("CRITICAL", "LEVEL_1")):
        return "CRITICAL"
    if any(token in resolved for token in ("MAJOR", "HIGH", "LEVEL_2")):
        return "HIGH"
    if any(token in resolved for token in ("OBSERVATION", "LOW", "LEVEL_4")):
        return "LOW"
    return "MEDIUM"


def link_qms_finding(
    db: Session,
    *,
    amo_id: str,
    finding_id: str,
    payload: QmsFindingLinkRequest,
    actor_user_id: str,
) -> schemas.ReliabilityIngestionResult:
    from amodb.apps.quality import models as quality_models

    finding = (
        db.query(quality_models.QMSAuditFinding)
        .filter(
            quality_models.QMSAuditFinding.amo_id == amo_id,
            quality_models.QMSAuditFinding.id == finding_id,
        )
        .first()
    )
    if not finding:
        raise HTTPException(status_code=404, detail="QMS finding not found in this tenant.")
    _assert_aircraft(db, amo_id=amo_id, aircraft_serial_number=payload.aircraft_serial_number)
    revision_at = max(
        [
            item
            for item in (
                finding.created_at,
                finding.acknowledged_at,
                finding.closed_at,
                finding.verified_at,
            )
            if item is not None
        ]
    )
    source_record_id = str(finding.id)
    source_revision = _utc(revision_at).isoformat()
    source = _ensure_source(
        db,
        amo_id=amo_id,
        spec=next(item for item in ADAPTER_SPECS if item.code == "QMS-FINDING-LINKS"),
        actor_user_id=actor_user_id,
    )
    record = {
        "external_id": _revisioned_external_id("QMS-FINDING-LINKS", source_record_id, source_revision),
        "event_type": payload.event_type,
        "occurred_at": _utc(finding.created_at).isoformat(),
        "aircraft_serial_number": payload.aircraft_serial_number,
        "ata_chapter": payload.ata_chapter,
        "reference_code": finding.finding_ref or source_record_id,
        "severity": payload.severity or _qms_severity(finding.severity, safety_sensitive=bool(finding.safety_sensitive)),
        "description": finding.description,
        "qms_finding_id": source_record_id,
        "qms_audit_id": str(finding.audit_id),
        "qms_finding_type": str(getattr(finding.finding_type, "value", finding.finding_type)),
        "qms_finding_level": str(getattr(finding.level, "value", finding.level)),
        "qms_requirement_reference": finding.requirement_ref,
        "qms_objective_evidence": finding.objective_evidence,
        "qms_safety_sensitive": bool(finding.safety_sensitive),
        "reliability_link_reason": payload.reliability_link_reason,
        "authoritative_source_record_id": source_record_id,
        "authoritative_source_revision": source_revision,
    }
    return services.ingest_batch(
        db,
        amo_id=amo_id,
        source=source,
        payload=schemas.ReliabilityBatchIngest(
            records=[record],
            metadata_json={
                "adapter": "qms-link-v1",
                "source_code": "QMS-FINDING-LINKS",
                "linked_by_user_id": actor_user_id,
                "reliability_link_reason": payload.reliability_link_reason,
            },
        ),
        actor_user_id=actor_user_id,
    )


def adapter_readiness(db: Session, *, amo_id: str) -> AdapterReadinessResponse:
    from amodb.apps.quality import models as quality_models

    sources = {
        item.code: item
        for item in db.query(domain.ReliabilitySource).filter(domain.ReliabilitySource.amo_id == amo_id).all()
    }
    source_counts = {
        source_id: int(count or 0)
        for source_id, count in db.query(
            domain.ReliabilityIngestionRecord.source_id,
            func.count(domain.ReliabilityIngestionRecord.id),
        )
        .filter(domain.ReliabilityIngestionRecord.amo_id == amo_id)
        .group_by(domain.ReliabilityIngestionRecord.source_id)
        .all()
    }
    scheduled_count, scheduled_latest = db.query(
        func.count(work_models.TaskCard.id),
        func.max(work_models.TaskCard.updated_at),
    ).join(
        work_models.WorkOrder,
        work_models.TaskCard.work_order_id == work_models.WorkOrder.id,
    ).filter(
        work_models.TaskCard.amo_id == amo_id,
        work_models.WorkOrder.amo_id == amo_id,
        work_models.TaskCard.origin_type == work_models.TaskOriginTypeEnum.NON_ROUTINE,
        work_models.WorkOrder.is_scheduled.is_(True),
    ).one()
    qms_count, qms_latest = db.query(
        func.count(quality_models.QMSAuditFinding.id),
        func.max(quality_models.QMSAuditFinding.created_at),
    ).filter(quality_models.QMSAuditFinding.amo_id == amo_id).one()

    items = [
        AdapterReadinessItem(
            code="SCHEDULED-CHECK-FINDINGS",
            module="Workpack / Work Orders",
            dataset="Non-routine findings raised during scheduled maintenance",
            implementation_state="READY",
            connection_state="WIRED_VIA_WORKPACK" if scheduled_count else "NO_DATA",
            source_id=(sources.get("WORKPACK-TASKS").id if sources.get("WORKPACK-TASKS") else None),
            available_record_count=int(scheduled_count or 0),
            ingested_record_count=0,
            latest_available_at=scheduled_latest,
            last_success_at=(sources.get("WORKPACK-TASKS").last_success_at if sources.get("WORKPACK-TASKS") else None),
            detail="Scheduled-check findings use WORKPACK-TASKS with an explicit scheduled-check provenance marker.",
        )
    ]
    for spec in ADAPTER_SPECS:
        source = sources.get(spec.code)
        available_count = int(qms_count or 0) if spec.code == "QMS-FINDING-LINKS" else 0
        latest_available = qms_latest if spec.code == "QMS-FINDING-LINKS" else None
        ingested_count = source_counts.get(source.id, 0) if source else 0
        if not source:
            connection_state = "CONFIGURATION_REQUIRED"
        elif ingested_count > 0 and source.last_success_at:
            connection_state = "WIRED"
        elif spec.implementation_state == "READY":
            connection_state = "LINK_READY"
        elif spec.implementation_state == "MAPPING_REQUIRED":
            connection_state = "MAPPING_REQUIRED"
        else:
            connection_state = "UPSTREAM_REQUIRED"
        items.append(
            AdapterReadinessItem(
                code=spec.code,
                module=spec.module,
                dataset=spec.dataset,
                implementation_state=spec.implementation_state,
                connection_state=connection_state,
                source_id=source.id if source else None,
                available_record_count=available_count,
                ingested_record_count=ingested_count,
                latest_available_at=latest_available,
                last_success_at=source.last_success_at if source else None,
                detail=spec.detail,
            )
        )
    return AdapterReadinessResponse(generated_at=datetime.now(timezone.utc), items=items)


def _context(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
) -> tuple[account_models.User, Session, str]:
    return current_user, db, services.tenant_id(current_user)


def configure_route(context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.source.manage")
    ensure_adapter_sources(db, amo_id=amo_id, actor_user_id=str(current_user.id))
    return adapter_readiness(db, amo_id=amo_id)


def readiness_route(context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.read")
    return adapter_readiness(db, amo_id=amo_id)


def flight_operations_route(payload: List[FlightOperationsOccurrence], context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ingest")
    return _ingest_records(
        db,
        amo_id=amo_id,
        code="FLIGHT-OPERATIONS",
        payloads=list(payload),
        actor_user_id=str(current_user.id),
    )


def deferral_route(payload: List[DeferralOccurrence], context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ingest")
    return _ingest_records(
        db,
        amo_id=amo_id,
        code="MEL-CDL",
        payloads=list(payload),
        actor_user_id=str(current_user.id),
    )


def component_shop_route(payload: List[ComponentShopOccurrence], context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ingest")
    return _ingest_records(
        db,
        amo_id=amo_id,
        code="COMPONENT-SHOP-FINDINGS",
        payloads=list(payload),
        actor_user_id=str(current_user.id),
    )


def sms_route(payload: List[SmsOccurrence], context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ingest")
    return _ingest_records(
        db,
        amo_id=amo_id,
        code="SMS-EVENTS",
        payloads=list(payload),
        actor_user_id=str(current_user.id),
    )


def historical_route(payload: List[HistoricalOccurrence], context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ingest")
    if any(item.reconciliation_status != "APPROVED" for item in payload):
        raise HTTPException(
            status_code=422,
            detail="Historical records must be approved before canonical Reliability ingestion.",
        )
    return _ingest_records(
        db,
        amo_id=amo_id,
        code="WORKBOOK-HISTORY",
        payloads=list(payload),
        actor_user_id=str(current_user.id),
    )


def qms_link_route(finding_id: str, payload: QmsFindingLinkRequest, context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ingest")
    return link_qms_finding(
        db,
        amo_id=amo_id,
        finding_id=finding_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


_REGISTERED = False


def register(router: APIRouter) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    _install_workpack_decorator()
    router.add_api_route(
        "/authoritative-sources/configure",
        configure_route,
        methods=["POST"],
        response_model=AdapterReadinessResponse,
        summary="Configure authoritative Reliability adapter contracts",
    )
    router.add_api_route(
        "/authoritative-sources/readiness",
        readiness_route,
        methods=["GET"],
        response_model=AdapterReadinessResponse,
        summary="Show authoritative source readiness without false wired states",
    )
    router.add_api_route(
        "/authoritative-sources/flight-operations/ingest",
        flight_operations_route,
        methods=["POST"],
        response_model=schemas.ReliabilityIngestionResult,
        status_code=status.HTTP_201_CREATED,
    )
    router.add_api_route(
        "/authoritative-sources/mel-cdl/ingest",
        deferral_route,
        methods=["POST"],
        response_model=schemas.ReliabilityIngestionResult,
        status_code=status.HTTP_201_CREATED,
    )
    router.add_api_route(
        "/authoritative-sources/component-shop/ingest",
        component_shop_route,
        methods=["POST"],
        response_model=schemas.ReliabilityIngestionResult,
        status_code=status.HTTP_201_CREATED,
    )
    router.add_api_route(
        "/authoritative-sources/sms/ingest",
        sms_route,
        methods=["POST"],
        response_model=schemas.ReliabilityIngestionResult,
        status_code=status.HTTP_201_CREATED,
    )
    router.add_api_route(
        "/authoritative-sources/workbook-history/ingest",
        historical_route,
        methods=["POST"],
        response_model=schemas.ReliabilityIngestionResult,
        status_code=status.HTTP_201_CREATED,
    )
    router.add_api_route(
        "/authoritative-sources/qms/findings/{finding_id}/link",
        qms_link_route,
        methods=["POST"],
        response_model=schemas.ReliabilityIngestionResult,
        status_code=status.HTTP_201_CREATED,
    )
    _REGISTERED = True
