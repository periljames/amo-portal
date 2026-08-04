from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.utils.identifiers import generate_uuid7
from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.tasks import models as task_models
from amodb.apps.work import models as work_models

from . import advanced_models as domain
from . import advanced_schemas as schemas
from . import models as legacy


ALL_CAPABILITIES = [
    "reliability.read",
    "reliability.source.manage",
    "reliability.ingest",
    "reliability.data_quality.resolve",
    "reliability.fracas.triage",
    "reliability.fracas.investigate",
    "reliability.fracas.action",
    "reliability.fracas.verify",
    "reliability.programme.manage",
    "reliability.programme.approve",
    "reliability.metric.manage",
    "reliability.metric.execute",
    "reliability.meeting.manage",
    "reliability.change.manage",
    "reliability.change.approve",
    "reliability.handoff.manage",
    "reliability.authority.prepare",
    "reliability.authority.submit",
    "reliability.ai.use",
    "reliability.ai.review",
    "reliability.audit.read",
]

FRACAS_TRANSITIONS: Dict[str, set[str]] = {
    "DETECTED": {"TRIAGE"},
    "TRIAGE": {"ACCEPTED", "REJECTED", "MERGED"},
    "ACCEPTED": {"CONTAINMENT"},
    "CONTAINMENT": {"INVESTIGATION"},
    "INVESTIGATION": {"ROOT_CAUSE_REVIEW"},
    "ROOT_CAUSE_REVIEW": {"ACTION_APPROVAL", "INVESTIGATION"},
    "ACTION_APPROVAL": {"IMPLEMENTATION", "INVESTIGATION"},
    "IMPLEMENTATION": {"EFFECTIVENESS"},
    "EFFECTIVENESS": {"CLOSED", "REOPENED"},
    "REOPENED": {"INVESTIGATION"},
    "REJECTED": set(),
    "MERGED": set(),
    "CLOSED": {"REOPENED"},
}

PROGRAMME_TRANSITIONS: Dict[str, set[str]] = {
    "DRAFT": {"IN_REVIEW", "REJECTED"},
    "IN_REVIEW": {"DRAFT", "APPROVED", "REJECTED"},
    "APPROVED": {"EFFECTIVE", "SUPERSEDED"},
    "EFFECTIVE": {"SUPERSEDED"},
    "SUPERSEDED": set(),
    "REJECTED": {"DRAFT"},
}

CHANGE_TRANSITIONS: Dict[str, set[str]] = {
    "DRAFT": {"TECH_REVIEW", "REJECTED"},
    "TECH_REVIEW": {"QUALITY_REVIEW", "DRAFT", "REJECTED"},
    "QUALITY_REVIEW": {"APPROVED", "TECH_REVIEW", "REJECTED"},
    "APPROVED": {"AUTHORITY_REVIEW", "IMPLEMENTED", "REJECTED"},
    "AUTHORITY_REVIEW": {"IMPLEMENTED", "REJECTED"},
    "IMPLEMENTED": {"CLOSED"},
    "REJECTED": {"DRAFT"},
    "CLOSED": set(),
}

MEETING_TRANSITIONS: Dict[str, set[str]] = {
    "DRAFT": {"AGENDA_LOCKED", "CANCELLED"},
    "AGENDA_LOCKED": {"HELD", "CANCELLED"},
    "HELD": {"APPROVED", "AGENDA_LOCKED"},
    "APPROVED": {"CLOSED"},
    "CLOSED": set(),
    "CANCELLED": set(),
}

AUTHORITY_TRANSITIONS: Dict[str, set[str]] = {
    "DRAFT": {"READY", "WITHDRAWN"},
    "READY": {"SUBMITTED", "DRAFT", "WITHDRAWN"},
    "SUBMITTED": {"ACKNOWLEDGED", "ACCEPTED", "REJECTED", "WITHDRAWN"},
    "ACKNOWLEDGED": {"ACCEPTED", "REJECTED", "WITHDRAWN"},
    "ACCEPTED": set(),
    "REJECTED": set(),
    "WITHDRAWN": set(),
}

EVENT_ALIASES = {
    "TECHNICAL_DELAY": "TECHNICAL_DELAY",
    "DELAY": "TECHNICAL_DELAY",
    "CANCELLATION": "TECHNICAL_CANCELLATION",
    "TECHNICAL_CANCELLATION": "TECHNICAL_CANCELLATION",
    "AIR_TURNBACK": "AIR_TURNBACK",
    "RETURN_TO_GATE": "RETURN_TO_GATE",
    "DIVERSION": "DIVERSION",
    "IN_FLIGHT_SHUTDOWN": "IN_FLIGHT_SHUTDOWN",
    "ABORTED_TAKEOFF": "ABORTED_TAKEOFF",
    "MEL": "MEL_DEFERRAL",
    "MEL_DEFERRAL": "MEL_DEFERRAL",
    "CDL": "CDL_DEFERRAL",
    "CDL_DEFERRAL": "CDL_DEFERRAL",
    "PILOT_REPORT": "PILOT_REPORT",
    "CABIN_REPORT": "CABIN_REPORT",
    "DEFECT": "DEFECT",
    "REPEAT_DEFECT": "REPEAT_DEFECT",
    "REMOVAL": "UNSCHEDULED_REMOVAL",
    "UNSCHEDULED_REMOVAL": "UNSCHEDULED_REMOVAL",
    "SCHEDULED_REMOVAL": "SCHEDULED_REMOVAL",
    "INSTALLATION": "INSTALLATION",
    "SHOP_FINDING": "SHOP_FINDING",
    "NO_FAULT_FOUND": "NO_FAULT_FOUND",
    "OCTM": "OCTM",
    "ECTM": "ECTM",
    "EHM_ALERT": "EHM_ALERT",
    "FRACAS": "FRACAS",
    "MAINTENANCE_ERROR": "MAINTENANCE_ERROR",
    "SUPPLIER_ESCAPE": "SUPPLIER_ESCAPE",
    "SAFETY_EVENT": "SAFETY_EVENT",
    "OTHER": "OTHER",
}

INTERRUPTION_EVENT_TYPES = {
    "TECHNICAL_DELAY",
    "TECHNICAL_CANCELLATION",
    "AIR_TURNBACK",
    "RETURN_TO_GATE",
    "DIVERSION",
    "IN_FLIGHT_SHUTDOWN",
    "ABORTED_TAKEOFF",
    "MEL_DEFERRAL",
    "CDL_DEFERRAL",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_datetime(value: Any, *, default: Optional[datetime] = None) -> Optional[datetime]:
    if value is None or value == "":
        return default
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        raw = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return default
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def decimal_value(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def quantize(value: Optional[Decimal], places: str = "0.00000001") -> Optional[Decimal]:
    if value is None:
        return None
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def tenant_id(user: account_models.User) -> str:
    amo_id = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if not amo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A tenant context is required.")
    return str(amo_id)


def capabilities_for_user(db: Session, user: account_models.User) -> List[str]:
    if getattr(user, "is_superuser", False):
        return list(ALL_CAPABILITIES)
    amo_id = tenant_id(user)
    try:
        rows = db.execute(
            text(
                """
                SELECT DISTINCT cd.code
                FROM auth_user_role_assignments ura
                JOIN auth_role_capability_bindings rcb ON rcb.role_id = ura.role_id
                JOIN auth_capability_definitions cd ON cd.id = rcb.capability_id
                WHERE ura.amo_id = :amo_id
                  AND ura.user_id = :user_id
                  AND cd.module = 'reliability'
                  AND (ura.valid_from IS NULL OR ura.valid_from <= CURRENT_TIMESTAMP)
                  AND (ura.valid_to IS NULL OR ura.valid_to >= CURRENT_TIMESTAMP)
                ORDER BY cd.code
                """
            ),
            {"amo_id": amo_id, "user_id": str(user.id)},
        ).scalars().all()
        return [str(row) for row in rows]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reliability authorization capability service unavailable.",
        ) from exc


def require_capability(db: Session, user: account_models.User, capability: str) -> None:
    if getattr(user, "is_superuser", False):
        return
    if capability not in capabilities_for_user(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Capability '{capability}' is required.",
        )


def append_audit(
    db: Session,
    *,
    amo_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    payload: Dict[str, Any],
    actor_user_id: Optional[str],
) -> domain.ReliabilityAuditEvent:
    previous = (
        db.query(domain.ReliabilityAuditEvent)
        .filter(
            domain.ReliabilityAuditEvent.amo_id == amo_id,
            domain.ReliabilityAuditEvent.entity_type == entity_type,
            domain.ReliabilityAuditEvent.entity_id == str(entity_id),
        )
        .order_by(domain.ReliabilityAuditEvent.created_at.desc(), domain.ReliabilityAuditEvent.id.desc())
        .first()
    )
    created_at = utcnow()
    previous_hash = previous.event_hash if previous else None
    event_hash = sha256_value(
        {
            "amo_id": amo_id,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action": action,
            "payload": payload,
            "actor_user_id": actor_user_id,
            "created_at": created_at.isoformat(),
            "previous_hash": previous_hash,
        }
    )
    event = domain.ReliabilityAuditEvent(
        amo_id=amo_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        payload_json=payload,
        actor_user_id=actor_user_id,
        previous_hash=previous_hash,
        event_hash=event_hash,
        created_at=created_at,
    )
    db.add(event)
    db.flush()
    return event


def list_audit_events(
    db: Session,
    *,
    amo_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = 200,
) -> Sequence[domain.ReliabilityAuditEvent]:
    query = db.query(domain.ReliabilityAuditEvent).filter(domain.ReliabilityAuditEvent.amo_id == amo_id)
    if entity_type:
        query = query.filter(domain.ReliabilityAuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(domain.ReliabilityAuditEvent.entity_id == str(entity_id))
    return query.order_by(domain.ReliabilityAuditEvent.created_at.desc()).limit(min(max(limit, 1), 500)).all()


def create_source(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.ReliabilitySourceCreate,
    actor_user_id: str,
) -> domain.ReliabilitySource:
    source = domain.ReliabilitySource(
        amo_id=amo_id,
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        source_type=payload.source_type,
        transport=payload.transport,
        mapping_version=payload.mapping_version,
        configuration_json=payload.configuration_json,
        poll_interval_minutes=payload.poll_interval_minutes,
        next_poll_at=(utcnow() if payload.transport == "INTERNAL" else None),
        created_by_user_id=actor_user_id,
    )
    db.add(source)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A Reliability source with this code already exists.") from exc
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="SOURCE",
        entity_id=source.id,
        action="SOURCE_CREATED",
        payload={"code": source.code, "source_type": source.source_type, "transport": source.transport},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(source)
    return source


def list_sources(db: Session, *, amo_id: str) -> Sequence[domain.ReliabilitySource]:
    return (
        db.query(domain.ReliabilitySource)
        .filter(domain.ReliabilitySource.amo_id == amo_id)
        .order_by(domain.ReliabilitySource.source_type.asc(), domain.ReliabilitySource.code.asc())
        .all()
    )


def get_source(db: Session, *, amo_id: str, source_id: str) -> domain.ReliabilitySource:
    source = (
        db.query(domain.ReliabilitySource)
        .filter(domain.ReliabilitySource.amo_id == amo_id, domain.ReliabilitySource.id == source_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Reliability source not found.")
    return source


def _normalise_event_type(value: Any) -> Optional[str]:
    if value is None:
        return None
    return EVENT_ALIASES.get(str(value).strip().upper())


def _validate_ingestion_record(payload: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    event_type = _normalise_event_type(payload.get("event_type") or payload.get("occurrence_type") or payload.get("type"))
    if not event_type:
        errors.append("event_type is missing or unsupported")
    if not parse_datetime(payload.get("occurred_at") or payload.get("event_time") or payload.get("date")):
        errors.append("occurred_at is missing or invalid")
    if event_type in {"DEFECT", "REPEAT_DEFECT", "UNSCHEDULED_REMOVAL", "SHOP_FINDING"} and not payload.get("ata_chapter"):
        warnings.append("ATA chapter is missing for a technical occurrence")
    if event_type in INTERRUPTION_EVENT_TYPES and not (
        payload.get("flight_number") or payload.get("techlog_no") or payload.get("reference_code")
    ):
        warnings.append("Operational interruption has no flight, tech-log or reference identifier")
    if event_type in {"MEL_DEFERRAL", "CDL_DEFERRAL"} and not (
        payload.get("mel_reference") or payload.get("cdl_reference")
    ):
        warnings.append("Deferral occurrence has no MEL/CDL reference")
    delay_value = payload.get("delay_minutes")
    if delay_value not in (None, ""):
        delay_error = "delay_minutes must be a nonnegative whole number"
        if isinstance(delay_value, bool):
            errors.append(delay_error)
        else:
            try:
                parsed_delay = Decimal(str(delay_value))
            except Exception:
                errors.append(delay_error)
            else:
                if (
                    not parsed_delay.is_finite()
                    or parsed_delay < 0
                    or parsed_delay != parsed_delay.to_integral_value()
                ):
                    errors.append(delay_error)
                else:
                    payload["delay_minutes"] = int(parsed_delay)
    return errors, warnings


def _record_external_id(payload: Dict[str, Any], payload_hash: str) -> str:
    value = (
        payload.get("external_id")
        or payload.get("source_record_id")
        or payload.get("operator_event_id")
        or payload.get("techlog_no")
        or payload.get("reference_code")
    )
    return str(value).strip()[:255] if value else payload_hash[:32]


def _create_data_issue(
    db: Session,
    *,
    amo_id: str,
    source_id: Optional[str],
    batch_id: Optional[str],
    record_id: Optional[str],
    code: str,
    severity: str,
    message: str,
    details: Dict[str, Any],
) -> domain.ReliabilityDataQualityIssue:
    issue = domain.ReliabilityDataQualityIssue(
        amo_id=amo_id,
        source_id=source_id,
        batch_id=batch_id,
        record_id=record_id,
        issue_code=code,
        severity=severity,
        message=message,
        details_json=details,
    )
    db.add(issue)
    db.flush()
    return issue


def ingest_batch(
    db: Session,
    *,
    amo_id: str,
    source: domain.ReliabilitySource,
    payload: schemas.ReliabilityBatchIngest,
    actor_user_id: Optional[str],
) -> schemas.ReliabilityIngestionResult:
    content_hash = sha256_value({"source": source.id, "records": payload.records, "metadata": payload.metadata_json})
    existing_batch = (
        db.query(domain.ReliabilityIngestionBatch)
        .filter(
            domain.ReliabilityIngestionBatch.amo_id == amo_id,
            domain.ReliabilityIngestionBatch.source_id == source.id,
            domain.ReliabilityIngestionBatch.content_hash == content_hash,
        )
        .first()
    )
    if existing_batch:
        return schemas.ReliabilityIngestionResult(
            batch=schemas.ReliabilityIngestionBatchRead.model_validate(existing_batch),
            duplicate_external_ids=["BATCH_ALREADY_PROCESSED"],
        )

    batch = domain.ReliabilityIngestionBatch(
        amo_id=amo_id,
        source_id=source.id,
        status="VALIDATING",
        content_hash=content_hash,
        record_count=len(payload.records),
        metadata_json=payload.metadata_json,
        received_by_user_id=actor_user_id,
    )
    db.add(batch)
    db.flush()

    created_event_ids: List[int] = []
    duplicates: List[str] = []
    rejected: List[Dict[str, Any]] = []

    for raw in payload.records:
        record_payload = dict(raw)
        payload_hash = sha256_value(record_payload)
        external_id = _record_external_id(record_payload, payload_hash)
        duplicate = (
            db.query(domain.ReliabilityIngestionRecord)
            .filter(
                domain.ReliabilityIngestionRecord.amo_id == amo_id,
                domain.ReliabilityIngestionRecord.source_id == source.id,
                or_(
                    domain.ReliabilityIngestionRecord.external_id == external_id,
                    domain.ReliabilityIngestionRecord.payload_hash == payload_hash,
                ),
            )
            .first()
        )
        if duplicate:
            duplicates.append(external_id)
            batch.duplicate_count += 1
            continue

        errors, warnings = _validate_ingestion_record(record_payload)
        ingestion_record = domain.ReliabilityIngestionRecord(
            amo_id=amo_id,
            source_id=source.id,
            batch_id=batch.id,
            external_id=external_id,
            payload_hash=payload_hash,
            payload_json=record_payload,
            validation_status="INVALID" if errors else ("WARNING" if warnings else "VALID"),
            validation_errors=[{"level": "ERROR", "message": item} for item in errors]
            + [{"level": "WARNING", "message": item} for item in warnings],
        )
        db.add(ingestion_record)
        db.flush()

        if errors:
            batch.invalid_count += 1
            rejected.append({"external_id": external_id, "errors": errors})
            _create_data_issue(
                db,
                amo_id=amo_id,
                source_id=source.id,
                batch_id=batch.id,
                record_id=ingestion_record.id,
                code="INGESTION_VALIDATION_FAILED",
                severity="HIGH",
                message="Reliability source record failed canonical validation.",
                details={"external_id": external_id, "errors": errors},
            )
            ingestion_record.processed_at = utcnow()
            continue

        event_type = _normalise_event_type(
            record_payload.get("event_type") or record_payload.get("occurrence_type") or record_payload.get("type")
        ) or "OTHER"
        severity_value = str(record_payload.get("severity") or "MEDIUM").upper()
        if severity_value not in {item.value for item in legacy.ReliabilitySeverityEnum}:
            severity_value = "MEDIUM"
        occurred_at = parse_datetime(
            record_payload.get("occurred_at") or record_payload.get("event_time") or record_payload.get("date"),
            default=utcnow(),
        )
        event = legacy.ReliabilityEvent(
            amo_id=amo_id,
            aircraft_serial_number=record_payload.get("aircraft_serial_number") or record_payload.get("aircraft_id"),
            engine_position=record_payload.get("engine_position"),
            component_id=record_payload.get("component_id"),
            work_order_id=record_payload.get("work_order_id"),
            task_card_id=record_payload.get("task_card_id"),
            event_type=legacy.ReliabilityEventTypeEnum(event_type),
            operator_event_id=(str(record_payload.get("operator_event_id"))[:36] if record_payload.get("operator_event_id") else None),
            severity=legacy.ReliabilitySeverityEnum(severity_value),
            ata_chapter=record_payload.get("ata_chapter"),
            reference_code=record_payload.get("reference_code") or record_payload.get("techlog_no"),
            source_system=source.code,
            description=record_payload.get("description") or record_payload.get("summary") or record_payload.get("title"),
            occurred_at=occurred_at,
            created_by_user_id=actor_user_id,
            source_record_id=external_id,
            source_payload_hash=payload_hash,
            validation_status="WARNING" if warnings else "VALID",
            validation_errors=[{"level": "WARNING", "message": item} for item in warnings],
            operation_stage=record_payload.get("operation_stage"),
            flight_number=record_payload.get("flight_number"),
            origin_station=record_payload.get("origin") or record_payload.get("origin_station"),
            destination_station=record_payload.get("destination") or record_payload.get("destination_station"),
            delay_minutes=record_payload.get("delay_minutes"),
            mel_reference=record_payload.get("mel_reference"),
            cdl_reference=record_payload.get("cdl_reference"),
            deferral_expires_at=parse_datetime(record_payload.get("deferred_until") or record_payload.get("deferral_expires_at")),
            part_number=record_payload.get("part_number"),
            component_serial_number=record_payload.get("component_serial_number") or record_payload.get("serial_number"),
            confirmed_failure=record_payload.get("confirmed_failure"),
            repeat_key=record_payload.get("repeat_key"),
            provenance_json={
                "source_id": source.id,
                "batch_id": batch.id,
                "record_id": ingestion_record.id,
                "mapping_version": source.mapping_version,
            },
        )
        db.add(event)
        db.flush()
        ingestion_record.normalized_event_id = event.id
        ingestion_record.processed_at = utcnow()
        batch.valid_count += 1
        created_event_ids.append(event.id)

        if event_type in INTERRUPTION_EVENT_TYPES:
            interruption = domain.ReliabilityOperationalInterruption(
                amo_id=amo_id,
                reliability_event_id=event.id,
                interruption_type=event_type,
                flight_number=record_payload.get("flight_number"),
                origin=record_payload.get("origin") or record_payload.get("origin_station"),
                destination=record_payload.get("destination") or record_payload.get("destination_station"),
                scheduled_departure_at=parse_datetime(record_payload.get("scheduled_departure_at")),
                actual_departure_at=parse_datetime(record_payload.get("actual_departure_at")),
                delay_minutes=record_payload.get("delay_minutes"),
                cancelled=bool(record_payload.get("cancelled") or event_type == "TECHNICAL_CANCELLATION"),
                return_to_gate=bool(record_payload.get("return_to_gate") or event_type == "RETURN_TO_GATE"),
                air_turnback=bool(record_payload.get("air_turnback") or event_type == "AIR_TURNBACK"),
                diversion=bool(record_payload.get("diversion") or event_type == "DIVERSION"),
                engine_shutdown=bool(record_payload.get("engine_shutdown") or event_type == "IN_FLIGHT_SHUTDOWN"),
                dispatch_impact=record_payload.get("dispatch_impact"),
                mel_reference=record_payload.get("mel_reference"),
                cdl_reference=record_payload.get("cdl_reference"),
                deferral_category=record_payload.get("deferral_category"),
                deferred_until=parse_datetime(record_payload.get("deferred_until")),
                notes=record_payload.get("interruption_notes"),
            )
            db.add(interruption)

        for warning in warnings:
            _create_data_issue(
                db,
                amo_id=amo_id,
                source_id=source.id,
                batch_id=batch.id,
                record_id=ingestion_record.id,
                code="INGESTION_WARNING",
                severity="MEDIUM",
                message=warning,
                details={"external_id": external_id, "event_id": event.id},
            )

    batch.status = "PROCESSED" if batch.invalid_count == 0 else ("FAILED" if batch.valid_count == 0 else "PARTIAL")
    batch.completed_at = utcnow()
    source.last_received_at = batch.received_at
    if batch.valid_count:
        source.last_success_at = batch.completed_at
        source.last_failure_at = None
    if batch.invalid_count:
        source.last_failure_at = batch.completed_at
    if source.poll_interval_minutes:
        source.next_poll_at = utcnow() + timedelta(minutes=source.poll_interval_minutes)
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="INGESTION_BATCH",
        entity_id=batch.id,
        action="BATCH_PROCESSED",
        payload={
            "source_id": source.id,
            "record_count": batch.record_count,
            "valid_count": batch.valid_count,
            "duplicate_count": batch.duplicate_count,
            "invalid_count": batch.invalid_count,
            "status": batch.status,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(batch)
    return schemas.ReliabilityIngestionResult(
        batch=schemas.ReliabilityIngestionBatchRead.model_validate(batch),
        created_event_ids=created_event_ids,
        duplicate_external_ids=duplicates,
        rejected_records=rejected,
    )


def list_batches(
    db: Session,
    *,
    amo_id: str,
    source_id: Optional[str] = None,
    limit: int = 100,
) -> Sequence[domain.ReliabilityIngestionBatch]:
    query = db.query(domain.ReliabilityIngestionBatch).filter(domain.ReliabilityIngestionBatch.amo_id == amo_id)
    if source_id:
        query = query.filter(domain.ReliabilityIngestionBatch.source_id == source_id)
    return query.order_by(domain.ReliabilityIngestionBatch.received_at.desc()).limit(min(max(limit, 1), 500)).all()


def list_data_quality_issues(
    db: Session,
    *,
    amo_id: str,
    issue_status: Optional[str] = None,
    source_id: Optional[str] = None,
    limit: int = 200,
) -> Sequence[domain.ReliabilityDataQualityIssue]:
    query = db.query(domain.ReliabilityDataQualityIssue).filter(domain.ReliabilityDataQualityIssue.amo_id == amo_id)
    if issue_status:
        query = query.filter(domain.ReliabilityDataQualityIssue.status == issue_status)
    if source_id:
        query = query.filter(domain.ReliabilityDataQualityIssue.source_id == source_id)
    return query.order_by(domain.ReliabilityDataQualityIssue.created_at.desc()).limit(min(max(limit, 1), 500)).all()


def resolve_data_quality_issue(
    db: Session,
    *,
    amo_id: str,
    issue_id: str,
    payload: schemas.DataQualityResolution,
    actor_user_id: str,
) -> domain.ReliabilityDataQualityIssue:
    issue = (
        db.query(domain.ReliabilityDataQualityIssue)
        .filter(domain.ReliabilityDataQualityIssue.amo_id == amo_id, domain.ReliabilityDataQualityIssue.id == issue_id)
        .first()
    )
    if not issue:
        raise HTTPException(status_code=404, detail="Data-quality issue not found.")
    if issue.status not in {"OPEN", "REOPENED"}:
        raise HTTPException(status_code=409, detail="Only open data-quality issues can be resolved or waived.")
    issue.status = payload.status
    issue.resolution = payload.resolution
    issue.resolved_at = utcnow()
    issue.resolved_by_user_id = actor_user_id
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="DATA_QUALITY_ISSUE",
        entity_id=issue.id,
        action=f"ISSUE_{payload.status}",
        payload={"resolution": payload.resolution},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(issue)
    return issue


def event_provenance(db: Session, *, amo_id: str, event_id: int) -> schemas.OccurrenceProvenance:
    event = (
        db.query(legacy.ReliabilityEvent)
        .filter(legacy.ReliabilityEvent.amo_id == amo_id, legacy.ReliabilityEvent.id == event_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Reliability occurrence not found.")
    record = (
        db.query(domain.ReliabilityIngestionRecord)
        .filter(
            domain.ReliabilityIngestionRecord.amo_id == amo_id,
            domain.ReliabilityIngestionRecord.normalized_event_id == event_id,
        )
        .first()
    )
    source = record.batch.source if record else None
    batch = record.batch if record else None
    interruption = (
        db.query(domain.ReliabilityOperationalInterruption)
        .filter(
            domain.ReliabilityOperationalInterruption.amo_id == amo_id,
            domain.ReliabilityOperationalInterruption.reliability_event_id == event_id,
        )
        .first()
    )
    return schemas.OccurrenceProvenance(
        event_id=event_id,
        source=schemas.ReliabilitySourceRead.model_validate(source) if source else None,
        batch=schemas.ReliabilityIngestionBatchRead.model_validate(batch) if batch else None,
        external_id=record.external_id if record else getattr(event, "source_record_id", None),
        payload_hash=record.payload_hash if record else getattr(event, "source_payload_hash", None),
        validation_status=record.validation_status if record else getattr(event, "validation_status", None),
        validation_errors=list(record.validation_errors or []) if record else list(getattr(event, "validation_errors", None) or []),
        raw_payload=dict(record.payload_json or {}) if record else None,
        interruption={
            column.name: getattr(interruption, column.name)
            for column in interruption.__table__.columns
            if column.name not in {"amo_id"}
        } if interruption else None,
    )


def harvest_internal_sources(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str] = None,
) -> List[schemas.ReliabilityIngestionResult]:
    results: List[schemas.ReliabilityIngestionResult] = []
    sources = (
        db.query(domain.ReliabilitySource)
        .filter(
            domain.ReliabilitySource.amo_id == amo_id,
            domain.ReliabilitySource.status == "ACTIVE",
            domain.ReliabilitySource.transport == "INTERNAL",
        )
        .all()
    )
    for source in sources:
        cursor = source.last_success_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
        records: List[Dict[str, Any]] = []
        if source.source_type in {"TECH_LOG", "MAINTENANCE"}:
            tasks = (
                db.query(work_models.TaskCard)
                .filter(
                    work_models.TaskCard.amo_id == amo_id,
                    work_models.TaskCard.category == work_models.TaskCategoryEnum.DEFECT,
                    work_models.TaskCard.created_at > cursor,
                )
                .order_by(work_models.TaskCard.created_at.asc())
                .limit(2000)
                .all()
            )
            for task in tasks:
                records.append(
                    {
                        "external_id": f"TASK_CARD:{task.id}",
                        "event_type": "DEFECT",
                        "occurred_at": task.created_at.isoformat(),
                        "aircraft_serial_number": task.aircraft_serial_number,
                        "ata_chapter": task.ata_chapter,
                        "reference_code": task.task_code or str(task.id),
                        "description": task.description or task.title,
                        "work_order_id": task.work_order_id,
                        "task_card_id": task.id,
                        "component_id": task.aircraft_component_id,
                        "repeat_key": f"{task.aircraft_serial_number}:{task.ata_chapter or 'UNK'}:{task.task_code or task.title}",
                    }
                )
        elif source.source_type == "EHM":
            shifts = (
                db.query(legacy.EngineTrendStatus)
                .filter(
                    legacy.EngineTrendStatus.amo_id == amo_id,
                    legacy.EngineTrendStatus.current_status == legacy.EngineTrendStatusEnum.SHIFT,
                    legacy.EngineTrendStatus.updated_at > cursor,
                )
                .order_by(legacy.EngineTrendStatus.updated_at.asc())
                .limit(2000)
                .all()
            )
            for shift in shifts:
                records.append(
                    {
                        "external_id": f"ENGINE_SHIFT:{shift.id}:{shift.updated_at.isoformat()}",
                        "event_type": "EHM_ALERT",
                        "occurred_at": shift.updated_at.isoformat(),
                        "aircraft_serial_number": shift.aircraft_serial_number,
                        "engine_position": shift.engine_position,
                        "severity": "HIGH",
                        "description": f"Engine trend shift for {shift.engine_position}",
                    }
                )
        if records:
            results.append(
                ingest_batch(
                    db,
                    amo_id=amo_id,
                    source=source,
                    payload=schemas.ReliabilityBatchIngest(
                        records=records,
                        metadata_json={"adapter": "internal", "cursor": cursor.isoformat()},
                    ),
                    actor_user_id=actor_user_id,
                )
            )
        else:
            source.last_success_at = utcnow()
            if source.poll_interval_minutes:
                source.next_poll_at = utcnow() + timedelta(minutes=source.poll_interval_minutes)
            db.commit()
    return results


def ensure_fracas_lifecycle(
    db: Session,
    *,
    amo_id: str,
    case_id: int,
    actor_user_id: Optional[str],
) -> domain.ReliabilityFracasLifecycle:
    case = (
        db.query(legacy.FRACASCase)
        .filter(legacy.FRACASCase.amo_id == amo_id, legacy.FRACASCase.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="FRACAS case not found.")
    lifecycle = (
        db.query(domain.ReliabilityFracasLifecycle)
        .filter(
            domain.ReliabilityFracasLifecycle.amo_id == amo_id,
            domain.ReliabilityFracasLifecycle.fracas_case_id == case_id,
        )
        .first()
    )
    if lifecycle:
        return lifecycle
    lifecycle = domain.ReliabilityFracasLifecycle(
        amo_id=amo_id,
        fracas_case_id=case_id,
        stage="DETECTED",
        owner_user_id=case.updated_by_user_id or case.created_by_user_id,
    )
    db.add(lifecycle)
    db.flush()
    _append_stage_event(
        db,
        lifecycle=lifecycle,
        from_stage=None,
        to_stage="DETECTED",
        decision="CASE_REGISTERED",
        rationale="Canonical FRACAS lifecycle created for the existing case.",
        payload={},
        actor_user_id=actor_user_id,
    )
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="FRACAS_CASE",
        entity_id=str(case_id),
        action="LIFECYCLE_CREATED",
        payload={"lifecycle_id": lifecycle.id},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(lifecycle)
    return lifecycle


def update_fracas_lifecycle(
    db: Session,
    *,
    amo_id: str,
    case_id: int,
    payload: schemas.FracasLifecycleUpdate,
    actor_user_id: str,
) -> domain.ReliabilityFracasLifecycle:
    lifecycle = ensure_fracas_lifecycle(db, amo_id=amo_id, case_id=case_id, actor_user_id=actor_user_id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(lifecycle, key, value)
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="FRACAS_CASE",
        entity_id=str(case_id),
        action="LIFECYCLE_UPDATED",
        payload=changes,
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(lifecycle)
    return lifecycle


def _append_stage_event(
    db: Session,
    *,
    lifecycle: domain.ReliabilityFracasLifecycle,
    from_stage: Optional[str],
    to_stage: str,
    decision: str,
    rationale: str,
    payload: Dict[str, Any],
    actor_user_id: Optional[str],
) -> domain.ReliabilityFracasStageEvent:
    previous = (
        db.query(domain.ReliabilityFracasStageEvent)
        .filter(domain.ReliabilityFracasStageEvent.lifecycle_id == lifecycle.id)
        .order_by(domain.ReliabilityFracasStageEvent.created_at.desc(), domain.ReliabilityFracasStageEvent.id.desc())
        .first()
    )
    created_at = utcnow()
    previous_hash = previous.event_hash if previous else None
    event_hash = sha256_value(
        {
            "lifecycle_id": lifecycle.id,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "decision": decision,
            "rationale": rationale,
            "payload": payload,
            "actor": actor_user_id,
            "created_at": created_at.isoformat(),
            "previous_hash": previous_hash,
        }
    )
    event = domain.ReliabilityFracasStageEvent(
        amo_id=lifecycle.amo_id,
        lifecycle_id=lifecycle.id,
        from_stage=from_stage,
        to_stage=to_stage,
        decision=decision,
        rationale=rationale,
        payload_json=payload,
        previous_hash=previous_hash,
        event_hash=event_hash,
        actor_user_id=actor_user_id,
        created_at=created_at,
    )
    db.add(event)
    db.flush()
    return event


def _legacy_fracas_status(stage: str) -> legacy.FRACASStatusEnum:
    if stage in {"DETECTED", "TRIAGE", "ACCEPTED", "CONTAINMENT"}:
        return legacy.FRACASStatusEnum.OPEN
    if stage in {"INVESTIGATION", "ROOT_CAUSE_REVIEW"}:
        return legacy.FRACASStatusEnum.IN_ANALYSIS
    if stage in {"ACTION_APPROVAL", "IMPLEMENTATION"}:
        return legacy.FRACASStatusEnum.ACTIONS
    if stage in {"EFFECTIVENESS", "REOPENED"}:
        return legacy.FRACASStatusEnum.MONITORING
    return legacy.FRACASStatusEnum.CLOSED


def _fracas_transition_preconditions(
    db: Session,
    *,
    lifecycle: domain.ReliabilityFracasLifecycle,
    to_stage: str,
    actor_user_id: str,
) -> None:
    case = lifecycle.case
    if to_stage == "INVESTIGATION" and lifecycle.containment_required and not lifecycle.containment_complete:
        raise HTTPException(status_code=409, detail="Containment must be completed before investigation.")
    if to_stage == "ROOT_CAUSE_REVIEW":
        if not lifecycle.problem_statement or not lifecycle.root_cause_method or not lifecycle.root_cause_json:
            raise HTTPException(status_code=409, detail="Problem statement, root-cause method and root-cause evidence are required.")
        evidence_count = db.query(func.count(domain.ReliabilityFracasEvidence.id)).filter(
            domain.ReliabilityFracasEvidence.lifecycle_id == lifecycle.id
        ).scalar() or 0
        if evidence_count < 1:
            raise HTTPException(status_code=409, detail="At least one immutable evidence record is required.")
    if to_stage == "ACTION_APPROVAL":
        actions = db.query(func.count(legacy.FRACASAction.id)).filter(
            legacy.FRACASAction.fracas_case_id == lifecycle.fracas_case_id
        ).scalar() or 0
        if actions < 1:
            raise HTTPException(status_code=409, detail="At least one corrective or preventive action is required.")
    if to_stage == "EFFECTIVENESS":
        incomplete = (
            db.query(func.count(legacy.FRACASAction.id))
            .filter(
                legacy.FRACASAction.fracas_case_id == lifecycle.fracas_case_id,
                legacy.FRACASAction.status.notin_([
                    legacy.FRACASActionStatusEnum.DONE,
                    legacy.FRACASActionStatusEnum.VERIFIED,
                    legacy.FRACASActionStatusEnum.CANCELLED,
                ]),
            )
            .scalar()
            or 0
        )
        if incomplete:
            raise HTTPException(status_code=409, detail="All FRACAS actions must be completed or cancelled before effectiveness review.")
    if to_stage == "CLOSED":
        effective_review = (
            db.query(domain.ReliabilityEffectivenessReview)
            .filter(
                domain.ReliabilityEffectivenessReview.lifecycle_id == lifecycle.id,
                domain.ReliabilityEffectivenessReview.outcome == "EFFECTIVE",
                domain.ReliabilityEffectivenessReview.approved_at.isnot(None),
            )
            .order_by(domain.ReliabilityEffectivenessReview.review_date.desc())
            .first()
        )
        if not effective_review:
            raise HTTPException(status_code=409, detail="An approved EFFECTIVE review is required before closure.")
        if case.created_by_user_id and str(case.created_by_user_id) == str(actor_user_id):
            raise HTTPException(status_code=409, detail="The case creator cannot independently close the FRACAS case.")


def transition_fracas(
    db: Session,
    *,
    amo_id: str,
    case_id: int,
    payload: schemas.FracasTransitionRequest,
    actor_user_id: str,
) -> domain.ReliabilityFracasLifecycle:
    lifecycle = ensure_fracas_lifecycle(db, amo_id=amo_id, case_id=case_id, actor_user_id=actor_user_id)
    allowed = FRACAS_TRANSITIONS.get(lifecycle.stage, set())
    if payload.to_stage not in allowed:
        raise HTTPException(status_code=409, detail=f"Transition {lifecycle.stage} -> {payload.to_stage} is not permitted.")
    _fracas_transition_preconditions(db, lifecycle=lifecycle, to_stage=payload.to_stage, actor_user_id=actor_user_id)
    previous_stage = lifecycle.stage
    lifecycle.stage = payload.to_stage
    lifecycle.stage_entered_at = utcnow()
    if payload.to_stage == "REOPENED":
        lifecycle.reopened_count += 1
    case = lifecycle.case
    case.status = _legacy_fracas_status(payload.to_stage)
    case.updated_by_user_id = actor_user_id
    if payload.to_stage == "CLOSED":
        case.closed_at = utcnow()
        case.verified_at = utcnow()
        case.verified_by_user_id = actor_user_id
    elif payload.to_stage == "REOPENED":
        case.closed_at = None
    _append_stage_event(
        db,
        lifecycle=lifecycle,
        from_stage=previous_stage,
        to_stage=payload.to_stage,
        decision=payload.decision,
        rationale=payload.rationale,
        payload=payload.payload_json,
        actor_user_id=actor_user_id,
    )
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="FRACAS_CASE",
        entity_id=str(case_id),
        action="STAGE_TRANSITION",
        payload={
            "from_stage": previous_stage,
            "to_stage": payload.to_stage,
            "decision": payload.decision,
            "rationale": payload.rationale,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(lifecycle)
    return lifecycle


def add_fracas_evidence(
    db: Session,
    *,
    amo_id: str,
    case_id: int,
    payload: schemas.FracasEvidenceCreate,
    actor_user_id: str,
) -> domain.ReliabilityFracasEvidence:
    lifecycle = ensure_fracas_lifecycle(db, amo_id=amo_id, case_id=case_id, actor_user_id=actor_user_id)
    source_hash = sha256_value(
        {
            "evidence_type": payload.evidence_type,
            "reference_type": payload.reference_type,
            "reference_id": payload.reference_id,
            "reference_url": payload.reference_url,
            "title": payload.title,
            "description": payload.description,
            "metadata_json": payload.metadata_json,
        }
    )
    evidence = domain.ReliabilityFracasEvidence(
        amo_id=amo_id,
        lifecycle_id=lifecycle.id,
        evidence_type=payload.evidence_type,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        reference_url=payload.reference_url,
        title=payload.title,
        description=payload.description,
        source_hash=source_hash,
        metadata_json=payload.metadata_json,
        captured_by_user_id=actor_user_id,
    )
    db.add(evidence)
    db.flush()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="FRACAS_CASE",
        entity_id=str(case_id),
        action="EVIDENCE_CAPTURED",
        payload={"evidence_id": evidence.id, "source_hash": source_hash, "title": evidence.title},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(evidence)
    return evidence


def list_fracas_evidence(db: Session, *, amo_id: str, case_id: int) -> Sequence[domain.ReliabilityFracasEvidence]:
    lifecycle = ensure_fracas_lifecycle(db, amo_id=amo_id, case_id=case_id, actor_user_id=None)
    return (
        db.query(domain.ReliabilityFracasEvidence)
        .filter(domain.ReliabilityFracasEvidence.amo_id == amo_id, domain.ReliabilityFracasEvidence.lifecycle_id == lifecycle.id)
        .order_by(domain.ReliabilityFracasEvidence.captured_at.asc())
        .all()
    )


def list_fracas_stage_events(db: Session, *, amo_id: str, case_id: int) -> Sequence[domain.ReliabilityFracasStageEvent]:
    lifecycle = ensure_fracas_lifecycle(db, amo_id=amo_id, case_id=case_id, actor_user_id=None)
    return (
        db.query(domain.ReliabilityFracasStageEvent)
        .filter(domain.ReliabilityFracasStageEvent.amo_id == amo_id, domain.ReliabilityFracasStageEvent.lifecycle_id == lifecycle.id)
        .order_by(domain.ReliabilityFracasStageEvent.created_at.asc())
        .all()
    )


def create_effectiveness_review(
    db: Session,
    *,
    amo_id: str,
    case_id: int,
    payload: schemas.EffectivenessReviewCreate,
    actor_user_id: str,
) -> domain.ReliabilityEffectivenessReview:
    lifecycle = ensure_fracas_lifecycle(db, amo_id=amo_id, case_id=case_id, actor_user_id=actor_user_id)
    if lifecycle.stage not in {"EFFECTIVENESS", "REOPENED", "CLOSED"}:
        raise HTTPException(status_code=409, detail="Effectiveness reviews are only allowed after implementation.")
    review = domain.ReliabilityEffectivenessReview(
        amo_id=amo_id,
        lifecycle_id=lifecycle.id,
        review_date=payload.review_date,
        metric_code=payload.metric_code,
        baseline_value=payload.baseline_value,
        current_value=payload.current_value,
        acceptance_criteria=payload.acceptance_criteria,
        outcome=payload.outcome,
        evidence_json=payload.evidence_json,
        notes=payload.notes,
        reviewer_user_id=actor_user_id,
        approved_by_user_id=None,
        approved_at=None,
    )
    db.add(review)
    db.flush()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="FRACAS_CASE",
        entity_id=str(case_id),
        action="EFFECTIVENESS_REVIEW_RECORDED",
        payload={"review_id": review.id, "outcome": review.outcome, "approved": False},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(review)
    return review


def approve_effectiveness_review(
    db: Session,
    *,
    amo_id: str,
    case_id: int,
    review_id: str,
    rationale: str,
    actor_user_id: str,
) -> domain.ReliabilityEffectivenessReview:
    lifecycle = ensure_fracas_lifecycle(db, amo_id=amo_id, case_id=case_id, actor_user_id=actor_user_id)
    review = (
        db.query(domain.ReliabilityEffectivenessReview)
        .filter(
            domain.ReliabilityEffectivenessReview.amo_id == amo_id,
            domain.ReliabilityEffectivenessReview.lifecycle_id == lifecycle.id,
            domain.ReliabilityEffectivenessReview.id == review_id,
        )
        .first()
    )
    if not review:
        raise HTTPException(status_code=404, detail="Effectiveness review not found.")
    if review.approved_at:
        raise HTTPException(status_code=409, detail="Effectiveness review is already approved.")
    if str(review.reviewer_user_id) == str(actor_user_id):
        raise HTTPException(status_code=409, detail="The effectiveness reviewer cannot approve their own review.")
    review.approved_by_user_id = actor_user_id
    review.approved_at = utcnow()
    review.notes = f"{review.notes or ''}\nApproval rationale: {rationale}".strip()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="FRACAS_CASE",
        entity_id=str(case_id),
        action="EFFECTIVENESS_REVIEW_APPROVED",
        payload={"review_id": review.id, "outcome": review.outcome, "rationale": rationale},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(review)
    return review


def list_effectiveness_reviews(db: Session, *, amo_id: str, case_id: int) -> Sequence[domain.ReliabilityEffectivenessReview]:
    lifecycle = ensure_fracas_lifecycle(db, amo_id=amo_id, case_id=case_id, actor_user_id=None)
    return (
        db.query(domain.ReliabilityEffectivenessReview)
        .filter(domain.ReliabilityEffectivenessReview.amo_id == amo_id, domain.ReliabilityEffectivenessReview.lifecycle_id == lifecycle.id)
        .order_by(domain.ReliabilityEffectivenessReview.review_date.desc())
        .all()
    )


def create_programme(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.ProgrammeCreate,
    actor_user_id: str,
) -> domain.ReliabilityProgramme:
    programme = domain.ReliabilityProgramme(
        amo_id=amo_id,
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        description=payload.description,
        owner_user_id=payload.owner_user_id or actor_user_id,
    )
    db.add(programme)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A Reliability programme with this code already exists.") from exc
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="PROGRAMME",
        entity_id=programme.id,
        action="PROGRAMME_CREATED",
        payload={"code": programme.code, "name": programme.name},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(programme)
    return programme


def list_programmes(db: Session, *, amo_id: str) -> Sequence[domain.ReliabilityProgramme]:
    return db.query(domain.ReliabilityProgramme).filter(domain.ReliabilityProgramme.amo_id == amo_id).order_by(domain.ReliabilityProgramme.code).all()


def create_programme_version(
    db: Session,
    *,
    amo_id: str,
    programme_id: str,
    payload: schemas.ProgrammeVersionCreate,
    actor_user_id: str,
) -> domain.ReliabilityProgrammeVersion:
    programme = (
        db.query(domain.ReliabilityProgramme)
        .filter(domain.ReliabilityProgramme.amo_id == amo_id, domain.ReliabilityProgramme.id == programme_id)
        .first()
    )
    if not programme:
        raise HTTPException(status_code=404, detail="Reliability programme not found.")
    matrix = payload.responsibility_matrix_json
    profiles = set(payload.regulatory_profiles)
    decision_authority = str(matrix.get("decision_authority", "")).upper()
    if "EASA_CAMO" in profiles and "CAMO" not in decision_authority:
        raise HTTPException(status_code=422, detail="EASA CAMO programme versions must retain CAMO decision authority.")
    if "FAA_CASS" in profiles and not any(token in decision_authority for token in {"OPERATOR", "CERTIFICATE_HOLDER"}):
        raise HTTPException(status_code=422, detail="FAA CASS programme versions must retain operator/certificate-holder decision authority.")
    version = domain.ReliabilityProgrammeVersion(
        amo_id=amo_id,
        programme_id=programme_id,
        revision=payload.revision,
        effective_from=payload.effective_from,
        change_summary=payload.change_summary,
        regulatory_profiles=list(payload.regulatory_profiles),
        scope_json=payload.scope_json,
        data_sources_json=payload.data_sources_json,
        reporting_json=payload.reporting_json,
        responsibility_matrix_json=payload.responsibility_matrix_json,
        authority_required=payload.authority_required,
        created_by_user_id=actor_user_id,
    )
    db.add(version)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This programme revision already exists.") from exc
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="PROGRAMME_VERSION",
        entity_id=version.id,
        action="VERSION_CREATED",
        payload={"programme_id": programme_id, "revision": version.revision, "profiles": version.regulatory_profiles},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(version)
    return version


def list_programme_versions(
    db: Session,
    *,
    amo_id: str,
    programme_id: Optional[str] = None,
) -> Sequence[domain.ReliabilityProgrammeVersion]:
    query = db.query(domain.ReliabilityProgrammeVersion).filter(domain.ReliabilityProgrammeVersion.amo_id == amo_id)
    if programme_id:
        query = query.filter(domain.ReliabilityProgrammeVersion.programme_id == programme_id)
    return query.order_by(domain.ReliabilityProgrammeVersion.created_at.desc()).all()


def transition_programme_version(
    db: Session,
    *,
    amo_id: str,
    version_id: str,
    payload: schemas.ProgrammeTransitionRequest,
    actor_user_id: str,
) -> domain.ReliabilityProgrammeVersion:
    version = (
        db.query(domain.ReliabilityProgrammeVersion)
        .filter(domain.ReliabilityProgrammeVersion.amo_id == amo_id, domain.ReliabilityProgrammeVersion.id == version_id)
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Programme version not found.")
    if payload.to_status not in PROGRAMME_TRANSITIONS.get(version.status, set()):
        raise HTTPException(status_code=409, detail=f"Programme transition {version.status} -> {payload.to_status} is not permitted.")
    if payload.to_status == "APPROVED":
        if str(version.created_by_user_id) == str(actor_user_id):
            raise HTTPException(status_code=409, detail="The programme-version author cannot approve their own version.")
        metric_count = db.query(func.count(domain.ReliabilityMetricDefinition.id)).filter(
            domain.ReliabilityMetricDefinition.programme_version_id == version.id,
            domain.ReliabilityMetricDefinition.active.is_(True),
        ).scalar() or 0
        if metric_count < 1:
            raise HTTPException(status_code=409, detail="At least one active governed metric is required before approval.")
        if not version.data_sources_json:
            raise HTTPException(status_code=409, detail="Approved programme versions require declared data sources.")
        version.approved_by_user_id = actor_user_id
        version.approved_at = utcnow()
        version.approval_json = {**(version.approval_json or {}), "approved_rationale": payload.rationale}
    if payload.to_status == "EFFECTIVE":
        if version.authority_required:
            accepted = (
                db.query(domain.ReliabilityAuthoritySubmission)
                .filter(
                    domain.ReliabilityAuthoritySubmission.amo_id == amo_id,
                    domain.ReliabilityAuthoritySubmission.programme_version_id == version.id,
                    domain.ReliabilityAuthoritySubmission.status == "ACCEPTED",
                )
                .first()
            )
            if not accepted:
                raise HTTPException(status_code=409, detail="Authority acceptance is required before this programme becomes effective.")
        previous_versions = (
            db.query(domain.ReliabilityProgrammeVersion)
            .filter(
                domain.ReliabilityProgrammeVersion.programme_id == version.programme_id,
                domain.ReliabilityProgrammeVersion.status == "EFFECTIVE",
                domain.ReliabilityProgrammeVersion.id != version.id,
            )
            .all()
        )
        for previous in previous_versions:
            previous.status = "SUPERSEDED"
            previous.effective_to = date.today()
        version.effective_from = version.effective_from or date.today()
    old_status = version.status
    version.status = payload.to_status
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="PROGRAMME_VERSION",
        entity_id=version.id,
        action="STATUS_TRANSITION",
        payload={"from": old_status, "to": payload.to_status, "rationale": payload.rationale},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(version)
    return version


def create_metric_definition(
    db: Session,
    *,
    amo_id: str,
    version_id: str,
    payload: schemas.MetricDefinitionCreate,
    actor_user_id: str,
) -> domain.ReliabilityMetricDefinition:
    version = (
        db.query(domain.ReliabilityProgrammeVersion)
        .filter(domain.ReliabilityProgrammeVersion.amo_id == amo_id, domain.ReliabilityProgrammeVersion.id == version_id)
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Programme version not found.")
    if version.status not in {"DRAFT", "IN_REVIEW"}:
        raise HTTPException(status_code=409, detail="Metrics can only be changed on a draft or in-review programme version.")
    metric = domain.ReliabilityMetricDefinition(
        amo_id=amo_id,
        programme_version_id=version_id,
        code=payload.code.strip().upper(),
        name=payload.name,
        description=payload.description,
        scope_type=payload.scope_type,
        method=payload.method,
        numerator_event_types=[_normalise_event_type(item) or item.upper() for item in payload.numerator_event_types],
        denominator_type=payload.denominator_type,
        multiplier=payload.multiplier,
        window_days=payload.window_days,
        schedule_interval_minutes=payload.schedule_interval_minutes,
        minimum_exposure=payload.minimum_exposure,
        direction=payload.direction,
        formula_version=payload.formula_version,
        next_run_at=utcnow(),
    )
    db.add(metric)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This metric code already exists in the programme version.") from exc
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="METRIC_DEFINITION",
        entity_id=metric.id,
        action="METRIC_CREATED",
        payload=payload.model_dump(mode="json"),
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(metric)
    return metric


def list_metrics(
    db: Session,
    *,
    amo_id: str,
    programme_version_id: Optional[str] = None,
) -> Sequence[domain.ReliabilityMetricDefinition]:
    query = db.query(domain.ReliabilityMetricDefinition).filter(domain.ReliabilityMetricDefinition.amo_id == amo_id)
    if programme_version_id:
        query = query.filter(domain.ReliabilityMetricDefinition.programme_version_id == programme_version_id)
    return query.order_by(domain.ReliabilityMetricDefinition.code.asc()).all()


def create_threshold(
    db: Session,
    *,
    amo_id: str,
    metric_id: str,
    payload: schemas.ThresholdCreate,
    actor_user_id: str,
) -> domain.ReliabilityThresholdVersion:
    metric = (
        db.query(domain.ReliabilityMetricDefinition)
        .filter(domain.ReliabilityMetricDefinition.amo_id == amo_id, domain.ReliabilityMetricDefinition.id == metric_id)
        .first()
    )
    if not metric:
        raise HTTPException(status_code=404, detail="Metric definition not found.")
    threshold = domain.ReliabilityThresholdVersion(
        amo_id=amo_id,
        metric_definition_id=metric_id,
        version=payload.version,
        caution_value=payload.caution_value,
        alert_value=payload.alert_value,
        lower_caution_value=payload.lower_caution_value,
        lower_alert_value=payload.lower_alert_value,
        minimum_exposure=payload.minimum_exposure,
        rationale=payload.rationale,
        effective_from=payload.effective_from,
        created_by_user_id=actor_user_id,
    )
    db.add(threshold)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This threshold version already exists.") from exc
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="THRESHOLD",
        entity_id=threshold.id,
        action="THRESHOLD_CREATED",
        payload=payload.model_dump(mode="json"),
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(threshold)
    return threshold


def list_thresholds(
    db: Session,
    *,
    amo_id: str,
    metric_id: Optional[str] = None,
) -> Sequence[domain.ReliabilityThresholdVersion]:
    query = db.query(domain.ReliabilityThresholdVersion).filter(domain.ReliabilityThresholdVersion.amo_id == amo_id)
    if metric_id:
        query = query.filter(domain.ReliabilityThresholdVersion.metric_definition_id == metric_id)
    return query.order_by(domain.ReliabilityThresholdVersion.created_at.desc()).all()


def transition_threshold(
    db: Session,
    *,
    amo_id: str,
    threshold_id: str,
    payload: schemas.ThresholdTransitionRequest,
    actor_user_id: str,
) -> domain.ReliabilityThresholdVersion:
    threshold = (
        db.query(domain.ReliabilityThresholdVersion)
        .filter(domain.ReliabilityThresholdVersion.amo_id == amo_id, domain.ReliabilityThresholdVersion.id == threshold_id)
        .first()
    )
    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold version not found.")
    allowed = {
        "DRAFT": {"APPROVED", "REJECTED"},
        "APPROVED": {"EFFECTIVE", "SUPERSEDED"},
        "EFFECTIVE": {"SUPERSEDED"},
        "SUPERSEDED": set(),
        "REJECTED": {"DRAFT"},
    }
    if payload.to_status not in allowed.get(threshold.status, set()):
        raise HTTPException(status_code=409, detail=f"Threshold transition {threshold.status} -> {payload.to_status} is not permitted.")
    if payload.to_status in {"APPROVED", "EFFECTIVE"} and str(threshold.created_by_user_id) == str(actor_user_id):
        raise HTTPException(status_code=409, detail="The threshold author cannot approve or activate their own threshold.")
    old = threshold.status
    threshold.status = payload.to_status
    if payload.to_status in {"APPROVED", "EFFECTIVE"}:
        threshold.approved_by_user_id = actor_user_id
        threshold.approved_at = utcnow()
    if payload.to_status == "EFFECTIVE":
        previous = (
            db.query(domain.ReliabilityThresholdVersion)
            .filter(
                domain.ReliabilityThresholdVersion.metric_definition_id == threshold.metric_definition_id,
                domain.ReliabilityThresholdVersion.status == "EFFECTIVE",
                domain.ReliabilityThresholdVersion.id != threshold.id,
            )
            .all()
        )
        for item in previous:
            item.status = "SUPERSEDED"
            item.effective_to = date.today()
        threshold.effective_from = threshold.effective_from or date.today()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="THRESHOLD",
        entity_id=threshold.id,
        action="STATUS_TRANSITION",
        payload={"from": old, "to": payload.to_status, "rationale": payload.rationale},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(threshold)
    return threshold


def _period_bounds(metric: domain.ReliabilityMetricDefinition, start: Optional[date], end: Optional[date]) -> Tuple[date, date]:
    period_end = end or date.today()
    period_start = start or (period_end - timedelta(days=max(metric.window_days - 1, 0)))
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="period_start must not be after period_end.")
    return period_start, period_end


def _scope_event_query(
    db: Session,
    *,
    amo_id: str,
    period_start: date,
    period_end: date,
    event_types: Sequence[str],
    scope_type: str,
    scope_id: str,
):
    start_dt = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(period_end, time.max, tzinfo=timezone.utc)
    query = db.query(legacy.ReliabilityEvent).filter(
        legacy.ReliabilityEvent.amo_id == amo_id,
        legacy.ReliabilityEvent.occurred_at >= start_dt,
        legacy.ReliabilityEvent.occurred_at <= end_dt,
    )
    if event_types:
        query = query.filter(legacy.ReliabilityEvent.event_type.in_([legacy.ReliabilityEventTypeEnum(item) for item in event_types]))
    if scope_type == "AIRCRAFT":
        query = query.filter(legacy.ReliabilityEvent.aircraft_serial_number == scope_id)
    elif scope_type == "ATA":
        query = query.filter(legacy.ReliabilityEvent.ata_chapter == scope_id)
    elif scope_type == "COMPONENT":
        query = query.filter(legacy.ReliabilityEvent.part_number == scope_id)
    elif scope_type == "ENGINE":
        query = query.filter(legacy.ReliabilityEvent.engine_position == scope_id)
    return query


def _exposure(
    db: Session,
    *,
    amo_id: str,
    period_start: date,
    period_end: date,
    denominator_type: str,
    scope_type: str,
    scope_id: str,
) -> Decimal:
    usage = db.query(fleet_models.AircraftUsage).filter(
        fleet_models.AircraftUsage.amo_id == amo_id,
        fleet_models.AircraftUsage.date >= period_start,
        fleet_models.AircraftUsage.date <= period_end,
    )
    if scope_type == "AIRCRAFT":
        usage = usage.filter(fleet_models.AircraftUsage.aircraft_serial_number == scope_id)
    if denominator_type == "FH":
        value = usage.with_entities(func.coalesce(func.sum(fleet_models.AircraftUsage.block_hours), 0)).scalar()
    elif denominator_type == "FC":
        value = usage.with_entities(func.coalesce(func.sum(fleet_models.AircraftUsage.cycles), 0)).scalar()
    elif denominator_type == "FLIGHTS":
        value = usage.with_entities(func.count(fleet_models.AircraftUsage.id)).scalar()
    elif denominator_type == "DAYS":
        value = Decimal(str((period_end - period_start).days + 1))
    elif denominator_type == "POPULATION":
        aircraft = db.query(fleet_models.Aircraft).filter(
            fleet_models.Aircraft.amo_id == amo_id,
            fleet_models.Aircraft.is_active.is_(True),
        )
        if scope_type == "AIRCRAFT":
            aircraft = aircraft.filter(fleet_models.Aircraft.serial_number == scope_id)
        value = aircraft.with_entities(func.count(fleet_models.Aircraft.serial_number)).scalar()
    else:
        value = Decimal("1")
    return decimal_value(value)


def _metric_event_contract(
    *,
    method: str,
    configured_event_types: Sequence[str],
) -> Tuple[List[str], Optional[List[str]], Optional[str]]:
    """Resolve numerator and event-denominator semantics for governed metrics."""
    numerator_types = [str(item) for item in configured_event_types]
    if method == "PERCENT":
        return numerator_types, [], "ALL_RELIABILITY_EVENTS"
    if method == "NFF_RATE":
        return ["NO_FAULT_FOUND"], ["UNSCHEDULED_REMOVAL"], "UNSCHEDULED_REMOVALS"
    return numerator_types, None, None


def _advance_metric_schedule(
    metric: domain.ReliabilityMetricDefinition,
    source_cutoff: datetime,
) -> None:
    metric.last_run_at = source_cutoff
    metric.next_run_at = source_cutoff + timedelta(
        minutes=max(int(metric.schedule_interval_minutes or 0), 60)
    )


def _rate_with_confidence(
    *,
    events: int,
    exposure: Decimal,
    multiplier: Decimal,
    method: str,
) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    if method == "COUNT":
        return Decimal(events), Decimal(events), Decimal(events)
    if exposure <= 0:
        return None, None, None
    if method == "MTBUR":
        value = exposure / Decimal(events) if events else None
        return quantize(value), None, None
    if method in {"PERCENT", "NFF_RATE"}:
        value = Decimal(events) / exposure * multiplier
        return quantize(value), None, None
    value = Decimal(events) / exposure * multiplier
    if events == 0:
        lower = Decimal("0")
        upper = Decimal("3") / exposure * multiplier
    else:
        standard_error = Decimal(str(math.sqrt(events))) / exposure * multiplier
        lower = max(Decimal("0"), value - Decimal("1.96") * standard_error)
        upper = value + Decimal("1.96") * standard_error
    return quantize(value), quantize(lower), quantize(upper)


def _active_threshold(
    db: Session,
    *,
    amo_id: str,
    metric_id: str,
    on_date: date,
) -> Optional[domain.ReliabilityThresholdVersion]:
    return (
        db.query(domain.ReliabilityThresholdVersion)
        .filter(
            domain.ReliabilityThresholdVersion.amo_id == amo_id,
            domain.ReliabilityThresholdVersion.metric_definition_id == metric_id,
            domain.ReliabilityThresholdVersion.status == "EFFECTIVE",
            or_(domain.ReliabilityThresholdVersion.effective_from.is_(None), domain.ReliabilityThresholdVersion.effective_from <= on_date),
            or_(domain.ReliabilityThresholdVersion.effective_to.is_(None), domain.ReliabilityThresholdVersion.effective_to >= on_date),
        )
        .order_by(domain.ReliabilityThresholdVersion.approved_at.desc())
        .first()
    )


def _evaluate_threshold(
    *,
    metric: domain.ReliabilityMetricDefinition,
    threshold: Optional[domain.ReliabilityThresholdVersion],
    value: Optional[Decimal],
    exposure: Decimal,
) -> Tuple[str, Optional[str]]:
    minimum = decimal_value(threshold.minimum_exposure if threshold and threshold.minimum_exposure is not None else metric.minimum_exposure)
    if exposure < minimum:
        return "INSUFFICIENT_DATA", None
    if value is None or not threshold:
        return "VALID", None
    if metric.direction in {"ABOVE", "TWO_SIDED"}:
        if threshold.alert_value is not None and value >= decimal_value(threshold.alert_value):
            return "ALERT", "HIGH"
        if threshold.caution_value is not None and value >= decimal_value(threshold.caution_value):
            return "CAUTION", "MEDIUM"
    if metric.direction in {"BELOW", "TWO_SIDED"}:
        if threshold.lower_alert_value is not None and value <= decimal_value(threshold.lower_alert_value):
            return "ALERT", "HIGH"
        if threshold.lower_caution_value is not None and value <= decimal_value(threshold.lower_caution_value):
            return "CAUTION", "MEDIUM"
    return "VALID", None


def execute_metric(
    db: Session,
    *,
    amo_id: str,
    metric: domain.ReliabilityMetricDefinition,
    period_start: Optional[date],
    period_end: Optional[date],
    scope_type: Optional[str],
    scope_id: Optional[str],
    actor_user_id: Optional[str],
    scheduled: bool,
) -> domain.ReliabilityCalculationRun:
    resolved_scope_type = scope_type or metric.scope_type
    resolved_scope_id = scope_id or "FLEET"
    start, end = _period_bounds(metric, period_start, period_end)
    configured_event_types = [str(item) for item in (metric.numerator_event_types or [])]
    event_types, denominator_event_types, denominator_source = _metric_event_contract(
        method=metric.method,
        configured_event_types=configured_event_types,
    )
    query = _scope_event_query(
        db,
        amo_id=amo_id,
        period_start=start,
        period_end=end,
        event_types=event_types,
        scope_type=resolved_scope_type,
        scope_id=resolved_scope_id,
    )
    events = query.count()
    if denominator_event_types is None:
        exposure = _exposure(
            db,
            amo_id=amo_id,
            period_start=start,
            period_end=end,
            denominator_type=metric.denominator_type,
            scope_type=resolved_scope_type,
            scope_id=resolved_scope_id,
        )
    else:
        denominator_query = _scope_event_query(
            db,
            amo_id=amo_id,
            period_start=start,
            period_end=end,
            event_types=denominator_event_types,
            scope_type=resolved_scope_type,
            scope_id=resolved_scope_id,
        )
        exposure = Decimal(denominator_query.count())
    value, lower, upper = _rate_with_confidence(
        events=events,
        exposure=exposure,
        multiplier=decimal_value(metric.multiplier, Decimal("1")),
        method=metric.method,
    )
    active_aircraft = (
        db.query(func.count(fleet_models.Aircraft.serial_number))
        .filter(fleet_models.Aircraft.amo_id == amo_id, fleet_models.Aircraft.is_active.is_(True))
        .scalar()
        or 0
    )
    threshold = _active_threshold(db, amo_id=amo_id, metric_id=metric.id, on_date=end)
    result_status, alert_severity = _evaluate_threshold(
        metric=metric,
        threshold=threshold,
        value=value,
        exposure=exposure,
    )
    source_cutoff = utcnow()
    lineage = {
        "event_types": event_types,
        "event_count": events,
        "denominator_type": denominator_source or metric.denominator_type,
        "configured_denominator_type": metric.denominator_type,
        "denominator_event_types": denominator_event_types,
        "exposure": str(exposure),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "scope_type": resolved_scope_type,
        "scope_id": resolved_scope_id,
        "threshold_id": threshold.id if threshold else None,
        "source_cutoff_at": source_cutoff.isoformat(),
    }
    result_hash = sha256_value(
        {
            "metric_id": metric.id,
            "formula_version": metric.formula_version,
            "lineage": lineage,
            "value": str(value) if value is not None else None,
            "confidence": [str(lower) if lower is not None else None, str(upper) if upper is not None else None],
            "status": result_status,
        }
    )
    existing = (
        db.query(domain.ReliabilityCalculationRun)
        .filter(
            domain.ReliabilityCalculationRun.amo_id == amo_id,
            domain.ReliabilityCalculationRun.metric_definition_id == metric.id,
            domain.ReliabilityCalculationRun.scope_type == resolved_scope_type,
            domain.ReliabilityCalculationRun.scope_id == resolved_scope_id,
            domain.ReliabilityCalculationRun.period_start == start,
            domain.ReliabilityCalculationRun.period_end == end,
            domain.ReliabilityCalculationRun.formula_version == metric.formula_version,
        )
        .first()
    )
    if existing:
        run = existing
        run.numerator = Decimal(events)
        run.denominator = exposure
        run.value = value
        run.confidence_lower = lower
        run.confidence_upper = upper
        run.sample_size = events
        run.small_fleet = active_aircraft < 6
        run.status = result_status
        run.source_cutoff_at = source_cutoff
        run.source_lineage_json = lineage
        run.result_hash = result_hash
        run.scheduled = bool(run.scheduled or scheduled)
        if actor_user_id is not None:
            run.run_by_user_id = actor_user_id
        audit_action = "CALCULATION_REFRESHED"
    else:
        run = domain.ReliabilityCalculationRun(
            amo_id=amo_id,
            metric_definition_id=metric.id,
            scope_type=resolved_scope_type,
            scope_id=resolved_scope_id,
            period_start=start,
            period_end=end,
            numerator=Decimal(events),
            denominator=exposure,
            value=value,
            confidence_lower=lower,
            confidence_upper=upper,
            sample_size=events,
            small_fleet=active_aircraft < 6,
            status=result_status,
            formula_version=metric.formula_version,
            source_cutoff_at=source_cutoff,
            source_lineage_json=lineage,
            result_hash=result_hash,
            scheduled=scheduled,
            run_by_user_id=actor_user_id,
        )
        db.add(run)
        audit_action = "CALCULATION_EXECUTED"
    db.flush()
    _advance_metric_schedule(metric, source_cutoff)
    if alert_severity:
        alert_code = f"{metric.code}:{resolved_scope_type}:{resolved_scope_id}:{end.isoformat()}"
        open_alert = (
            db.query(legacy.ReliabilityAlert)
            .filter(
                legacy.ReliabilityAlert.amo_id == amo_id,
                legacy.ReliabilityAlert.alert_code == alert_code,
                legacy.ReliabilityAlert.status != legacy.ReliabilityAlertStatusEnum.CLOSED,
            )
            .first()
        )
        if not open_alert:
            db.add(
                legacy.ReliabilityAlert(
                    amo_id=amo_id,
                    alert_code=alert_code,
                    status=legacy.ReliabilityAlertStatusEnum.OPEN,
                    severity=legacy.ReliabilitySeverityEnum(alert_severity),
                    message=(
                        f"{metric.name} is {value} for {resolved_scope_type} {resolved_scope_id}; "
                        f"governed threshold version {threshold.version if threshold else 'none'}."
                    ),
                    created_by_user_id=actor_user_id,
                )
            )
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="CALCULATION_RUN",
        entity_id=run.id,
        action=audit_action,
        payload={
            "metric_id": metric.id,
            "status": result_status,
            "result_hash": result_hash,
            "scheduled": scheduled,
            "source_cutoff_at": source_cutoff.isoformat(),
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(run)
    return run


def execute_metric_by_id(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.CalculationExecuteRequest,
    actor_user_id: Optional[str],
    scheduled: bool = False,
) -> domain.ReliabilityCalculationRun:
    metric = (
        db.query(domain.ReliabilityMetricDefinition)
        .filter(domain.ReliabilityMetricDefinition.amo_id == amo_id, domain.ReliabilityMetricDefinition.id == payload.metric_definition_id)
        .first()
    )
    if not metric:
        raise HTTPException(status_code=404, detail="Metric definition not found.")
    return execute_metric(
        db,
        amo_id=amo_id,
        metric=metric,
        period_start=payload.period_start,
        period_end=payload.period_end,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        actor_user_id=actor_user_id,
        scheduled=scheduled,
    )


def _metric_scopes(db: Session, *, amo_id: str, metric: domain.ReliabilityMetricDefinition) -> List[str]:
    if metric.scope_type == "FLEET":
        return ["FLEET"]
    if metric.scope_type == "AIRCRAFT":
        return [
            str(row[0])
            for row in db.query(fleet_models.Aircraft.serial_number)
            .filter(fleet_models.Aircraft.amo_id == amo_id, fleet_models.Aircraft.is_active.is_(True))
            .all()
        ]
    column = {
        "ATA": legacy.ReliabilityEvent.ata_chapter,
        "COMPONENT": legacy.ReliabilityEvent.part_number,
        "ENGINE": legacy.ReliabilityEvent.engine_position,
    }.get(metric.scope_type)
    if column is None:
        return ["FLEET"]
    return [
        str(row[0])
        for row in db.query(column)
        .filter(legacy.ReliabilityEvent.amo_id == amo_id, column.isnot(None))
        .distinct()
        .all()
    ]


def run_due_metrics(
    db: Session,
    *,
    amo_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
) -> List[domain.ReliabilityCalculationRun]:
    now = utcnow()
    query = db.query(domain.ReliabilityMetricDefinition).filter(
        domain.ReliabilityMetricDefinition.active.is_(True),
        or_(domain.ReliabilityMetricDefinition.next_run_at.is_(None), domain.ReliabilityMetricDefinition.next_run_at <= now),
    )
    if amo_id:
        query = query.filter(domain.ReliabilityMetricDefinition.amo_id == amo_id)
    metrics = query.limit(500).all()
    runs: List[domain.ReliabilityCalculationRun] = []
    for metric in metrics:
        for scope_id in _metric_scopes(db, amo_id=metric.amo_id, metric=metric):
            runs.append(
                execute_metric(
                    db,
                    amo_id=metric.amo_id,
                    metric=metric,
                    period_start=None,
                    period_end=None,
                    scope_type=metric.scope_type,
                    scope_id=scope_id,
                    actor_user_id=actor_user_id,
                    scheduled=True,
                )
            )
    return runs


def list_calculation_runs(
    db: Session,
    *,
    amo_id: str,
    metric_id: Optional[str] = None,
    scope_type: Optional[str] = None,
    limit: int = 200,
) -> Sequence[domain.ReliabilityCalculationRun]:
    query = db.query(domain.ReliabilityCalculationRun).filter(domain.ReliabilityCalculationRun.amo_id == amo_id)
    if metric_id:
        query = query.filter(domain.ReliabilityCalculationRun.metric_definition_id == metric_id)
    if scope_type:
        query = query.filter(domain.ReliabilityCalculationRun.scope_type == scope_type)
    return query.order_by(domain.ReliabilityCalculationRun.created_at.desc()).limit(min(max(limit, 1), 500)).all()


def analytics(
    db: Session,
    *,
    amo_id: str,
    scope_type: str,
    period_start: date,
    period_end: date,
    denominator_type: str = "FH",
    multiplier: Decimal = Decimal("100"),
    event_types: Optional[List[str]] = None,
) -> schemas.AnalyticsResponse:
    scope_type = scope_type.upper()
    event_types = [_normalise_event_type(item) or item.upper() for item in (event_types or [])]
    if scope_type == "FLEET":
        scope_ids = ["FLEET"]
    elif scope_type == "AIRCRAFT":
        scope_ids = [
            str(row[0])
            for row in db.query(fleet_models.Aircraft.serial_number)
            .filter(fleet_models.Aircraft.amo_id == amo_id, fleet_models.Aircraft.is_active.is_(True))
            .all()
        ]
    else:
        column = {
            "ATA": legacy.ReliabilityEvent.ata_chapter,
            "COMPONENT": legacy.ReliabilityEvent.part_number,
            "ENGINE": legacy.ReliabilityEvent.engine_position,
        }.get(scope_type)
        if column is None:
            raise HTTPException(status_code=422, detail="Unsupported analytics scope.")
        scope_ids = [
            str(row[0])
            for row in db.query(column)
            .filter(legacy.ReliabilityEvent.amo_id == amo_id, column.isnot(None))
            .distinct()
            .all()
        ]
    rows: List[schemas.AnalyticsRow] = []
    fleet_size = db.query(func.count(fleet_models.Aircraft.serial_number)).filter(
        fleet_models.Aircraft.amo_id == amo_id, fleet_models.Aircraft.is_active.is_(True)
    ).scalar() or 0
    for scope_id in scope_ids:
        query = _scope_event_query(
            db,
            amo_id=amo_id,
            period_start=period_start,
            period_end=period_end,
            event_types=event_types,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        events = query.count()
        exposure = _exposure(
            db,
            amo_id=amo_id,
            period_start=period_start,
            period_end=period_end,
            denominator_type=denominator_type,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        value, lower, upper = _rate_with_confidence(events=events, exposure=exposure, multiplier=multiplier, method="RATE")
        details: Dict[str, Any] = {}
        if scope_type == "COMPONENT":
            removals = query.filter(legacy.ReliabilityEvent.event_type == legacy.ReliabilityEventTypeEnum.UNSCHEDULED_REMOVAL).count()
            nff = query.filter(legacy.ReliabilityEvent.event_type == legacy.ReliabilityEventTypeEnum.NO_FAULT_FOUND).count()
            mtbur = exposure / Decimal(removals) if removals and exposure else None
            details = {
                "unscheduled_removals": removals,
                "no_fault_found": nff,
                "nff_percent": str(quantize(Decimal(nff) / Decimal(removals) * Decimal("100")) if removals else Decimal("0")),
                "mtbur": str(quantize(mtbur)) if mtbur else None,
                "survival_probability_at_exposure": str(quantize(Decimal(str(math.exp(-1))) if mtbur else Decimal("1"))),
            }
        insufficient = exposure <= 0
        rows.append(
            schemas.AnalyticsRow(
                scope_type=scope_type,
                scope_id=scope_id,
                label=scope_id,
                events=events,
                exposure=exposure,
                rate=value,
                confidence_lower=lower,
                confidence_upper=upper,
                small_fleet=fleet_size < 6,
                status="INSUFFICIENT_DATA" if insufficient else "VALID",
                details=details,
            )
        )
    rows.sort(key=lambda row: (row.rate is not None, row.rate or Decimal("-1")), reverse=True)
    return schemas.AnalyticsResponse(
        generated_at=utcnow(),
        period_start=period_start,
        period_end=period_end,
        scope_type=scope_type,
        denominator_type=denominator_type,
        multiplier=multiplier,
        rows=rows,
    )


def create_meeting(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.MeetingCreate,
    actor_user_id: str,
) -> domain.ReliabilityReviewMeeting:
    meeting = domain.ReliabilityReviewMeeting(
        amo_id=amo_id,
        programme_version_id=payload.programme_version_id,
        meeting_type=payload.meeting_type,
        title=payload.title,
        scheduled_at=payload.scheduled_at,
        data_cutoff_at=payload.data_cutoff_at,
        agenda_json=payload.agenda_json,
        attendees_json=payload.attendees_json,
        quorum_json=payload.quorum_json,
        chaired_by_user_id=actor_user_id,
    )
    db.add(meeting)
    db.flush()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="MEETING",
        entity_id=meeting.id,
        action="MEETING_CREATED",
        payload={"title": meeting.title, "scheduled_at": meeting.scheduled_at.isoformat()},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(meeting)
    return meeting


def list_meetings(db: Session, *, amo_id: str) -> Sequence[domain.ReliabilityReviewMeeting]:
    return db.query(domain.ReliabilityReviewMeeting).filter(domain.ReliabilityReviewMeeting.amo_id == amo_id).order_by(
        domain.ReliabilityReviewMeeting.scheduled_at.desc()
    ).all()


def transition_meeting(
    db: Session,
    *,
    amo_id: str,
    meeting_id: str,
    payload: schemas.MeetingTransitionRequest,
    actor_user_id: str,
) -> domain.ReliabilityReviewMeeting:
    meeting = db.query(domain.ReliabilityReviewMeeting).filter(
        domain.ReliabilityReviewMeeting.amo_id == amo_id, domain.ReliabilityReviewMeeting.id == meeting_id
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Reliability meeting not found.")
    if payload.to_status not in MEETING_TRANSITIONS.get(meeting.status, set()):
        raise HTTPException(status_code=409, detail=f"Meeting transition {meeting.status} -> {payload.to_status} is not permitted.")
    if payload.to_status == "AGENDA_LOCKED":
        meeting.data_cutoff_at = meeting.data_cutoff_at or utcnow()
        if not meeting.agenda_json:
            raise HTTPException(status_code=409, detail="An agenda is required before locking the meeting data cut.")
    if payload.to_status == "HELD" and not meeting.attendees_json:
        raise HTTPException(status_code=409, detail="Meeting attendees must be recorded.")
    if payload.to_status == "APPROVED":
        if str(meeting.chaired_by_user_id) == str(actor_user_id):
            raise HTTPException(status_code=409, detail="The meeting chair cannot independently approve their own minutes.")
        meeting.minutes = payload.minutes or meeting.minutes
        if not meeting.minutes:
            raise HTTPException(status_code=409, detail="Meeting minutes are required before approval.")
        meeting.approved_by_user_id = actor_user_id
        meeting.approved_at = utcnow()
    old = meeting.status
    meeting.status = payload.to_status
    if payload.minutes:
        meeting.minutes = payload.minutes
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="MEETING",
        entity_id=meeting.id,
        action="STATUS_TRANSITION",
        payload={"from": old, "to": payload.to_status, "rationale": payload.rationale},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(meeting)
    return meeting


def add_meeting_decision(
    db: Session,
    *,
    amo_id: str,
    meeting_id: str,
    payload: schemas.MeetingDecisionCreate,
    actor_user_id: str,
) -> domain.ReliabilityMeetingDecision:
    meeting = db.query(domain.ReliabilityReviewMeeting).filter(
        domain.ReliabilityReviewMeeting.amo_id == amo_id, domain.ReliabilityReviewMeeting.id == meeting_id
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Reliability meeting not found.")
    decision = domain.ReliabilityMeetingDecision(
        amo_id=amo_id,
        meeting_id=meeting_id,
        **payload.model_dump(),
    )
    db.add(decision)
    db.flush()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="MEETING",
        entity_id=meeting_id,
        action="DECISION_RECORDED",
        payload={"decision_id": decision.id, "title": decision.title, "decision_type": decision.decision_type},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(decision)
    return decision


def list_meeting_decisions(db: Session, *, amo_id: str, meeting_id: str) -> Sequence[domain.ReliabilityMeetingDecision]:
    return db.query(domain.ReliabilityMeetingDecision).filter(
        domain.ReliabilityMeetingDecision.amo_id == amo_id, domain.ReliabilityMeetingDecision.meeting_id == meeting_id
    ).order_by(domain.ReliabilityMeetingDecision.created_at.asc()).all()


def create_change(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.ChangeProposalCreate,
    actor_user_id: str,
) -> domain.ReliabilityChangeProposal:
    proposal = domain.ReliabilityChangeProposal(
        amo_id=amo_id,
        created_by_user_id=actor_user_id,
        **payload.model_dump(),
    )
    db.add(proposal)
    db.flush()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="CHANGE_PROPOSAL",
        entity_id=proposal.id,
        action="CHANGE_CREATED",
        payload={"proposal_type": proposal.proposal_type, "source_type": proposal.source_type, "source_id": proposal.source_id},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(proposal)
    return proposal


def list_changes(db: Session, *, amo_id: str, change_status: Optional[str] = None) -> Sequence[domain.ReliabilityChangeProposal]:
    query = db.query(domain.ReliabilityChangeProposal).filter(domain.ReliabilityChangeProposal.amo_id == amo_id)
    if change_status:
        query = query.filter(domain.ReliabilityChangeProposal.status == change_status)
    return query.order_by(domain.ReliabilityChangeProposal.created_at.desc()).all()


def simulate_change(
    db: Session,
    *,
    amo_id: str,
    change_id: str,
    payload: schemas.ChangeSimulationRequest,
    actor_user_id: str,
) -> domain.ReliabilityChangeProposal:
    proposal = db.query(domain.ReliabilityChangeProposal).filter(
        domain.ReliabilityChangeProposal.amo_id == amo_id, domain.ReliabilityChangeProposal.id == change_id
    ).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Change proposal not found.")
    values = payload.model_dump()
    annual_hours = decimal_value(values.get("annual_utilisation_hours"))
    current_interval = decimal_value(values.get("current_interval"))
    proposed_interval = decimal_value(values.get("proposed_interval"))
    manhours = decimal_value(values.get("average_manhours"))
    material_cost = decimal_value(values.get("average_material_cost"))
    fleet_size = int(values.get("fleet_size") or 1)
    current_events = annual_hours / current_interval if annual_hours > 0 and current_interval > 0 else Decimal("0")
    proposed_events = annual_hours / proposed_interval if annual_hours > 0 and proposed_interval > 0 else Decimal("0")
    delta_events = (proposed_events - current_events) * Decimal(fleet_size)
    proposal.simulation_json = {
        "inputs": {key: str(value) if isinstance(value, Decimal) else value for key, value in values.items()},
        "current_annual_events": str(quantize(current_events) or Decimal("0")),
        "proposed_annual_events": str(quantize(proposed_events) or Decimal("0")),
        "fleet_delta_events": str(quantize(delta_events) or Decimal("0")),
        "fleet_delta_manhours": str(quantize(delta_events * manhours) or Decimal("0")),
        "fleet_delta_material_cost": str(quantize(delta_events * material_cost) or Decimal("0")),
        "warning": "This deterministic impact estimate does not replace engineering or authority approval.",
    }
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="CHANGE_PROPOSAL",
        entity_id=proposal.id,
        action="IMPACT_SIMULATED",
        payload=proposal.simulation_json,
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(proposal)
    return proposal


def transition_change(
    db: Session,
    *,
    amo_id: str,
    change_id: str,
    payload: schemas.ChangeTransitionRequest,
    actor_user_id: str,
) -> domain.ReliabilityChangeProposal:
    proposal = db.query(domain.ReliabilityChangeProposal).filter(
        domain.ReliabilityChangeProposal.amo_id == amo_id, domain.ReliabilityChangeProposal.id == change_id
    ).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Change proposal not found.")
    if payload.to_status not in CHANGE_TRANSITIONS.get(proposal.status, set()):
        raise HTTPException(status_code=409, detail=f"Change transition {proposal.status} -> {payload.to_status} is not permitted.")
    if payload.to_status == "APPROVED" and str(proposal.created_by_user_id) == str(actor_user_id):
        raise HTTPException(status_code=409, detail="The change author cannot approve their own proposal.")
    if payload.to_status in {"APPROVED", "IMPLEMENTED"} and not proposal.impact_assessment_json:
        raise HTTPException(status_code=409, detail="A controlled impact assessment is required.")
    if payload.to_status == "IMPLEMENTED" and not proposal.simulation_json:
        raise HTTPException(status_code=409, detail="A recorded impact simulation is required before implementation.")
    old = proposal.status
    proposal.status = payload.to_status
    proposal.approval_json = {
        **(proposal.approval_json or {}),
        payload.to_status: {
            "actor_user_id": actor_user_id,
            "rationale": payload.rationale,
            "at": utcnow().isoformat(),
            **payload.approval_json,
        },
    }
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="CHANGE_PROPOSAL",
        entity_id=proposal.id,
        action="STATUS_TRANSITION",
        payload={"from": old, "to": payload.to_status, "rationale": payload.rationale},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(proposal)
    return proposal


def create_handoff(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.HandoffCreate,
    actor_user_id: str,
) -> domain.ReliabilityHandoff:
    handoff = domain.ReliabilityHandoff(
        amo_id=amo_id,
        created_by_user_id=actor_user_id,
        **payload.model_dump(),
    )
    db.add(handoff)
    db.flush()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="HANDOFF",
        entity_id=handoff.id,
        action="HANDOFF_CREATED",
        payload={"target_module": handoff.target_module, "source_type": handoff.source_type, "source_id": handoff.source_id},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(handoff)
    return handoff


def list_handoffs(
    db: Session,
    *,
    amo_id: str,
    target_module: Optional[str] = None,
    handoff_status: Optional[str] = None,
) -> Sequence[domain.ReliabilityHandoff]:
    query = db.query(domain.ReliabilityHandoff).filter(domain.ReliabilityHandoff.amo_id == amo_id)
    if target_module:
        query = query.filter(domain.ReliabilityHandoff.target_module == target_module)
    if handoff_status:
        query = query.filter(domain.ReliabilityHandoff.status == handoff_status)
    return query.order_by(domain.ReliabilityHandoff.created_at.desc()).all()


def transition_handoff(
    db: Session,
    *,
    amo_id: str,
    handoff_id: str,
    payload: schemas.HandoffTransitionRequest,
    actor_user_id: str,
) -> domain.ReliabilityHandoff:
    handoff = db.query(domain.ReliabilityHandoff).filter(
        domain.ReliabilityHandoff.amo_id == amo_id, domain.ReliabilityHandoff.id == handoff_id
    ).first()
    if not handoff:
        raise HTTPException(status_code=404, detail="Reliability handoff not found.")
    allowed = {
        "DRAFT": {"SENT", "CANCELLED"},
        "SENT": {"ACKNOWLEDGED", "REJECTED", "CANCELLED"},
        "ACKNOWLEDGED": {"COMPLETED", "REJECTED"},
        "COMPLETED": set(),
        "REJECTED": {"SENT"},
        "CANCELLED": set(),
    }
    if payload.to_status not in allowed.get(handoff.status, set()):
        raise HTTPException(status_code=409, detail=f"Handoff transition {handoff.status} -> {payload.to_status} is not permitted.")
    old = handoff.status
    handoff.status = payload.to_status
    if payload.target_record_type:
        handoff.target_record_type = payload.target_record_type
    if payload.target_record_id:
        handoff.target_record_id = payload.target_record_id
    if payload.to_status == "SENT":
        handoff.sent_at = utcnow()
        if not handoff.task_id:
            task = task_models.Task(
                amo_id=amo_id,
                title=f"Reliability handoff to {handoff.target_module}",
                description=str(handoff.payload_json.get("summary") or handoff.payload_json.get("description") or payload.rationale)[:1024],
                status=task_models.TaskStatus.OPEN,
                owner_user_id=handoff.owner_user_id,
                entity_type="RELIABILITY_HANDOFF",
                entity_id=handoff.id,
                priority=int(handoff.payload_json.get("priority") or 2),
                metadata_json={
                    "target_module": handoff.target_module,
                    "target_route": handoff.target_route,
                    "source_type": handoff.source_type,
                    "source_id": handoff.source_id,
                },
            )
            db.add(task)
            db.flush()
            handoff.task_id = task.id
    elif payload.to_status == "ACKNOWLEDGED":
        handoff.acknowledged_at = utcnow()
        if handoff.task_id:
            task = db.get(task_models.Task, handoff.task_id)
            if task:
                task.status = task_models.TaskStatus.IN_PROGRESS
    elif payload.to_status == "COMPLETED":
        handoff.completed_at = utcnow()
        if handoff.task_id:
            task = db.get(task_models.Task, handoff.task_id)
            if task:
                task.status = task_models.TaskStatus.DONE
                task.closed_at = utcnow()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="HANDOFF",
        entity_id=handoff.id,
        action="STATUS_TRANSITION",
        payload={"from": old, "to": payload.to_status, "rationale": payload.rationale, "task_id": handoff.task_id},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(handoff)
    return handoff


def create_authority_submission(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.AuthoritySubmissionCreate,
    actor_user_id: str,
) -> domain.ReliabilityAuthoritySubmission:
    if not any([payload.programme_version_id, payload.change_proposal_id, payload.meeting_id]):
        raise HTTPException(status_code=422, detail="An authority submission must reference a programme version, change or meeting.")
    submission = domain.ReliabilityAuthoritySubmission(
        amo_id=amo_id,
        created_by_user_id=actor_user_id,
        **payload.model_dump(),
    )
    db.add(submission)
    db.flush()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="AUTHORITY_SUBMISSION",
        entity_id=submission.id,
        action="SUBMISSION_CREATED",
        payload={"authority_profile": submission.authority_profile, "submission_type": submission.submission_type},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(submission)
    return submission


def list_authority_submissions(db: Session, *, amo_id: str) -> Sequence[domain.ReliabilityAuthoritySubmission]:
    return db.query(domain.ReliabilityAuthoritySubmission).filter(
        domain.ReliabilityAuthoritySubmission.amo_id == amo_id
    ).order_by(domain.ReliabilityAuthoritySubmission.created_at.desc()).all()


def transition_authority_submission(
    db: Session,
    *,
    amo_id: str,
    submission_id: str,
    payload: schemas.AuthorityTransitionRequest,
    actor_user_id: str,
) -> domain.ReliabilityAuthoritySubmission:
    submission = db.query(domain.ReliabilityAuthoritySubmission).filter(
        domain.ReliabilityAuthoritySubmission.amo_id == amo_id,
        domain.ReliabilityAuthoritySubmission.id == submission_id,
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Authority submission not found.")
    if payload.to_status not in AUTHORITY_TRANSITIONS.get(submission.status, set()):
        raise HTTPException(status_code=409, detail=f"Authority transition {submission.status} -> {payload.to_status} is not permitted.")
    if payload.to_status == "READY":
        manifest = submission.package_manifest_json or {}
        required = {"source_cutoff_at", "evidence", "responsibility_statement", "approval_record"}
        missing = sorted(required - set(manifest))
        if missing:
            raise HTTPException(status_code=409, detail=f"Authority package manifest is missing: {', '.join(missing)}")
    if payload.to_status == "SUBMITTED":
        if submission.status != "READY":
            raise HTTPException(status_code=409, detail="Only a READY package can be submitted.")
        if str(submission.created_by_user_id) == str(actor_user_id):
            raise HTTPException(status_code=409, detail="The authority-package preparer cannot submit their own package.")
        submission.submitted_by_user_id = actor_user_id
        submission.submitted_at = utcnow()
    if payload.to_status in {"ACCEPTED", "REJECTED"}:
        submission.decision_at = utcnow()
    if payload.external_reference:
        submission.external_reference = payload.external_reference
    if payload.response_json:
        submission.response_json = {**(submission.response_json or {}), **payload.response_json}
    old = submission.status
    submission.status = payload.to_status
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="AUTHORITY_SUBMISSION",
        entity_id=submission.id,
        action="STATUS_TRANSITION",
        payload={"from": old, "to": payload.to_status, "rationale": payload.rationale},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(submission)
    return submission


def _ai_snapshot(db: Session, *, amo_id: str, entity_type: str, entity_id: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    entity_type_upper = entity_type.upper()
    citations: List[Dict[str, Any]] = []
    if entity_type_upper == "FRACAS_CASE":
        lifecycle = ensure_fracas_lifecycle(db, amo_id=amo_id, case_id=int(entity_id), actor_user_id=None)
        evidence = list_fracas_evidence(db, amo_id=amo_id, case_id=int(entity_id))
        actions = db.query(legacy.FRACASAction).filter(legacy.FRACASAction.fracas_case_id == int(entity_id)).all()
        snapshot = {
            "case": {
                "id": lifecycle.case.id,
                "title": lifecycle.case.title,
                "description": lifecycle.case.description,
                "severity": lifecycle.case.severity.value if lifecycle.case.severity else None,
            },
            "lifecycle": {
                "stage": lifecycle.stage,
                "problem_statement": lifecycle.problem_statement,
                "root_cause_method": lifecycle.root_cause_method,
                "root_cause_json": lifecycle.root_cause_json,
                "risk_assessment_json": lifecycle.risk_assessment_json,
            },
            "evidence_count": len(evidence),
            "actions": [
                {"id": action.id, "status": action.status.value, "description": action.description}
                for action in actions
            ],
        }
        citations.extend(
            {"type": "FRACAS_EVIDENCE", "id": item.id, "title": item.title, "hash": item.source_hash}
            for item in evidence
        )
        return snapshot, citations
    if entity_type_upper == "OCCURRENCE":
        event = db.query(legacy.ReliabilityEvent).filter(
            legacy.ReliabilityEvent.amo_id == amo_id, legacy.ReliabilityEvent.id == int(entity_id)
        ).first()
        if not event:
            raise HTTPException(status_code=404, detail="Occurrence not found.")
        provenance = event_provenance(db, amo_id=amo_id, event_id=event.id)
        snapshot = {
            "event": {
                column.name: getattr(event, column.name)
                for column in event.__table__.columns
                if column.name not in {"amo_id"}
            },
            "provenance": provenance.model_dump(mode="json"),
        }
        citations.append({"type": "RELIABILITY_EVENT", "id": str(event.id), "hash": getattr(event, "source_payload_hash", None)})
        return snapshot, citations
    if entity_type_upper == "CHANGE_PROPOSAL":
        proposal = db.query(domain.ReliabilityChangeProposal).filter(
            domain.ReliabilityChangeProposal.amo_id == amo_id, domain.ReliabilityChangeProposal.id == entity_id
        ).first()
        if not proposal:
            raise HTTPException(status_code=404, detail="Change proposal not found.")
        snapshot = {
            column.name: getattr(proposal, column.name)
            for column in proposal.__table__.columns
            if column.name not in {"amo_id"}
        }
        citations.append({"type": "CHANGE_PROPOSAL", "id": proposal.id})
        return snapshot, citations
    raise HTTPException(status_code=422, detail="Unsupported AI review entity type.")


def create_ai_review(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.AiReviewRequest,
    actor_user_id: str,
) -> domain.ReliabilityAiReview:
    snapshot, citations = _ai_snapshot(db, amo_id=amo_id, entity_type=payload.entity_type, entity_id=payload.entity_id)
    gaps: List[str] = []
    suggestions: List[str] = []
    if payload.entity_type.upper() == "FRACAS_CASE":
        lifecycle = snapshot["lifecycle"]
        if not lifecycle.get("problem_statement"):
            gaps.append("Problem statement is missing.")
        if not lifecycle.get("root_cause_json"):
            gaps.append("Root-cause evidence is not yet recorded.")
        if snapshot.get("evidence_count", 0) < 2:
            gaps.append("Evidence set is thin; corroborating technical evidence should be added.")
        incomplete = [item for item in snapshot.get("actions", []) if item["status"] not in {"DONE", "VERIFIED", "CANCELLED"}]
        if incomplete:
            suggestions.append(f"Review {len(incomplete)} incomplete action(s) before moving to effectiveness.")
    elif payload.entity_type.upper() == "OCCURRENCE":
        event = snapshot["event"]
        if not event.get("ata_chapter"):
            gaps.append("ATA chapter is missing.")
        if not event.get("source_payload_hash"):
            gaps.append("Source payload hash is missing; provenance is incomplete.")
        if event.get("repeat_key"):
            suggestions.append("Search the repeat key across the fleet before disposition.")
    elif payload.entity_type.upper() == "CHANGE_PROPOSAL":
        if not snapshot.get("impact_assessment_json"):
            gaps.append("Impact assessment is missing.")
        if not snapshot.get("simulation_json"):
            gaps.append("Impact simulation is missing.")
        suggestions.append("Confirm Planning, Maintenance and Quality handoffs before implementation.")
    output = {
        "summary": f"Advisory {payload.review_type.lower().replace('_', ' ')} review generated from {len(citations)} cited evidence record(s).",
        "evidence_gaps": gaps,
        "suggested_next_steps": suggestions,
        "instruction": payload.instruction,
        "prohibited_actions": [
            "No maintenance programme approval was made.",
            "No defect was deferred or cleared.",
            "No FRACAS case was closed.",
            "No authority submission was sent.",
        ],
    }
    prompt_hash = sha256_value({"review_type": payload.review_type, "instruction": payload.instruction, "snapshot": snapshot})
    confidence = Decimal("0.85") if not gaps else Decimal("0.62")
    review = domain.ReliabilityAiReview(
        amo_id=amo_id,
        review_type=payload.review_type,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        model_id=os.getenv("RELIABILITY_AI_MODEL_ID", "reliability-rules-engine"),
        model_version=os.getenv("RELIABILITY_AI_MODEL_VERSION", "1.0"),
        prompt_hash=prompt_hash,
        input_snapshot_json=snapshot,
        citations_json=citations,
        output_json=output,
        confidence=confidence,
        advisory_only=True,
        created_by_user_id=actor_user_id,
    )
    db.add(review)
    db.flush()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="AI_REVIEW",
        entity_id=review.id,
        action="ADVISORY_REVIEW_CREATED",
        payload={"review_type": review.review_type, "entity_type": review.entity_type, "entity_id": review.entity_id, "prompt_hash": prompt_hash},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(review)
    return review


def list_ai_reviews(db: Session, *, amo_id: str, entity_type: Optional[str] = None, entity_id: Optional[str] = None) -> Sequence[domain.ReliabilityAiReview]:
    query = db.query(domain.ReliabilityAiReview).filter(domain.ReliabilityAiReview.amo_id == amo_id)
    if entity_type:
        query = query.filter(domain.ReliabilityAiReview.entity_type == entity_type)
    if entity_id:
        query = query.filter(domain.ReliabilityAiReview.entity_id == entity_id)
    return query.order_by(domain.ReliabilityAiReview.created_at.desc()).limit(500).all()


def decide_ai_review(
    db: Session,
    *,
    amo_id: str,
    review_id: str,
    payload: schemas.AiReviewDecision,
    actor_user_id: str,
) -> domain.ReliabilityAiReview:
    review = db.query(domain.ReliabilityAiReview).filter(
        domain.ReliabilityAiReview.amo_id == amo_id, domain.ReliabilityAiReview.id == review_id
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="AI review not found.")
    if review.status not in {"DRAFT", "REVIEWED"}:
        raise HTTPException(status_code=409, detail="This AI review already has a final human decision.")
    if str(review.created_by_user_id) == str(actor_user_id):
        raise HTTPException(status_code=409, detail="The AI-review requester cannot provide the final human disposition.")
    review.status = payload.decision
    review.review_notes = payload.review_notes
    review.reviewed_by_user_id = actor_user_id
    review.reviewed_at = utcnow()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="AI_REVIEW",
        entity_id=review.id,
        action="HUMAN_DECISION_RECORDED",
        payload={"decision": payload.decision, "review_notes": payload.review_notes},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(review)
    return review


def compliance_overview(db: Session, *, amo_id: str) -> schemas.ComplianceOverview:
    now = utcnow()
    active_version = (
        db.query(domain.ReliabilityProgrammeVersion)
        .filter(domain.ReliabilityProgrammeVersion.amo_id == amo_id, domain.ReliabilityProgrammeVersion.status == "EFFECTIVE")
        .order_by(domain.ReliabilityProgrammeVersion.effective_from.desc())
        .first()
    )
    profiles = list(active_version.regulatory_profiles or []) if active_version else []
    checks: List[schemas.ComplianceCheck] = []
    checks.append(
        schemas.ComplianceCheck(
            code="PROGRAMME_EFFECTIVE",
            title="Controlled reliability programme",
            status="GREEN" if active_version else "RED",
            detail="An effective approved programme version is in force." if active_version else "No effective approved programme version exists.",
            route="program",
        )
    )
    sources = db.query(domain.ReliabilitySource).filter(domain.ReliabilitySource.amo_id == amo_id, domain.ReliabilitySource.status == "ACTIVE").all()
    stale_sources = [source for source in sources if not source.last_success_at or source.last_success_at < now - timedelta(days=7)]
    checks.append(
        schemas.ComplianceCheck(
            code="SOURCE_FRESHNESS",
            title="Declared source freshness",
            status="GREEN" if sources and not stale_sources else ("RED" if not sources else "AMBER"),
            detail=(
                f"{len(sources)} active source(s) are current."
                if sources and not stale_sources
                else f"{len(stale_sources)} source(s) are stale or have never succeeded."
            ),
            count=len(stale_sources),
            route="sources",
        )
    )
    open_dq = db.query(func.count(domain.ReliabilityDataQualityIssue.id)).filter(
        domain.ReliabilityDataQualityIssue.amo_id == amo_id,
        domain.ReliabilityDataQualityIssue.status == "OPEN",
    ).scalar() or 0
    checks.append(
        schemas.ComplianceCheck(
            code="DATA_QUALITY",
            title="Data-quality control",
            status="GREEN" if open_dq == 0 else "AMBER",
            detail=f"{open_dq} open data-quality issue(s).",
            count=open_dq,
            route="data-quality",
        )
    )
    effective_metrics = db.query(func.count(domain.ReliabilityMetricDefinition.id)).join(
        domain.ReliabilityProgrammeVersion,
        domain.ReliabilityMetricDefinition.programme_version_id == domain.ReliabilityProgrammeVersion.id,
    ).filter(
        domain.ReliabilityMetricDefinition.amo_id == amo_id,
        domain.ReliabilityMetricDefinition.active.is_(True),
        domain.ReliabilityProgrammeVersion.status == "EFFECTIVE",
    ).scalar() or 0
    checks.append(
        schemas.ComplianceCheck(
            code="GOVERNED_METRICS",
            title="Governed scheduled metrics",
            status="GREEN" if effective_metrics > 0 else "RED",
            detail=f"{effective_metrics} active metric definition(s) are governed by an effective programme.",
            count=effective_metrics,
            route="calculations",
        )
    )
    overdue_fracas = db.query(func.count(domain.ReliabilityFracasLifecycle.id)).filter(
        domain.ReliabilityFracasLifecycle.amo_id == amo_id,
        domain.ReliabilityFracasLifecycle.effectiveness_due_date.isnot(None),
        domain.ReliabilityFracasLifecycle.effectiveness_due_date < date.today(),
        domain.ReliabilityFracasLifecycle.stage.notin_(["CLOSED", "REJECTED", "MERGED"]),
    ).scalar() or 0
    checks.append(
        schemas.ComplianceCheck(
            code="FRACAS_EFFECTIVENESS",
            title="FRACAS effectiveness follow-up",
            status="GREEN" if overdue_fracas == 0 else "RED",
            detail=f"{overdue_fracas} FRACAS lifecycle(s) have overdue effectiveness review dates.",
            count=overdue_fracas,
            route="cases",
        )
    )
    draft_authority = db.query(func.count(domain.ReliabilityAuthoritySubmission.id)).filter(
        domain.ReliabilityAuthoritySubmission.amo_id == amo_id,
        domain.ReliabilityAuthoritySubmission.status.in_(["DRAFT", "READY"]),
    ).scalar() or 0
    checks.append(
        schemas.ComplianceCheck(
            code="AUTHORITY_PACKAGES",
            title="Authority-controlled packages",
            status="AMBER" if draft_authority else "GREEN",
            detail=f"{draft_authority} authority package(s) remain draft or ready for submission.",
            count=draft_authority,
            route="authority",
        )
    )
    statuses = {check.status for check in checks}
    overall = "RED" if "RED" in statuses else ("AMBER" if "AMBER" in statuses else ("GREEN" if statuses == {"GREEN"} else "UNKNOWN"))
    return schemas.ComplianceOverview(
        generated_at=now,
        overall_status=overall,
        regulatory_profiles=profiles,
        checks=checks,
        disclaimer=(
            "This control view demonstrates configured evidence and workflow gates. Regulatory compliance remains an accountable organisation decision and cannot be established by software status alone."
        ),
    )


def bootstrap_reliability(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
) -> schemas.BootstrapResult:
    created = {"programmes": 0, "versions": 0, "sources": 0, "metrics": 0, "thresholds": 0}
    programme = db.query(domain.ReliabilityProgramme).filter(
        domain.ReliabilityProgramme.amo_id == amo_id, domain.ReliabilityProgramme.code == "RP-001"
    ).first()
    if not programme:
        programme = domain.ReliabilityProgramme(
            amo_id=amo_id,
            code="RP-001",
            name="Controlled Fleet Reliability Programme",
            description="Operator/CAMO-controlled programme with contracted AMO analysis support and retained decision authority.",
            owner_user_id=actor_user_id,
        )
        db.add(programme)
        db.flush()
        created["programmes"] += 1
    version = db.query(domain.ReliabilityProgrammeVersion).filter(
        domain.ReliabilityProgrammeVersion.programme_id == programme.id,
        domain.ReliabilityProgrammeVersion.revision == "INITIAL",
    ).first()
    if not version:
        version = domain.ReliabilityProgrammeVersion(
            amo_id=amo_id,
            programme_id=programme.id,
            revision="INITIAL",
            status="DRAFT",
            change_summary="Initial controlled Reliability programme baseline.",
            regulatory_profiles=["EASA_CAMO", "EASA_PART145_PROVIDER", "FAA_CASS", "ICAO"],
            scope_json={"fleet": "ALL_ACTIVE", "aircraft_types": [], "operations": []},
            data_sources_json=[
                {"type": "TECH_LOG", "required": True},
                {"type": "FLIGHT_OPERATIONS", "required": True},
                {"type": "MAINTENANCE", "required": True},
                {"type": "EHM", "required": False},
            ],
            reporting_json={"monthly_review": True, "annual_programme_review": True},
            responsibility_matrix_json={
                "programme_owner": "CAMO_OR_CERTIFICATE_HOLDER",
                "analysis_provider": "AMO_RELIABILITY_FUNCTION",
                "decision_authority": "CAMO_OR_CERTIFICATE_HOLDER",
                "implementation_providers": ["PLANNING", "MAINTENANCE", "TECH_RECORDS", "QMS", "PROCUREMENT"],
            },
            created_by_user_id=actor_user_id,
        )
        db.add(version)
        db.flush()
        created["versions"] += 1
    source_specs = [
        ("TECHLOG-INTERNAL", "Maintenance defect task cards", "TECH_LOG", "INTERNAL", 60),
        ("OPS-PUSH", "Flight operations interruptions", "FLIGHT_OPERATIONS", "PUSH", None),
        ("MEL-CDL-PUSH", "MEL and CDL deferrals", "MEL_CDL", "PUSH", None),
        ("EHM-INTERNAL", "Engine trend shifts", "EHM", "INTERNAL", 60),
        ("SHOP-PUSH", "Component shop findings", "COMPONENT_SHOP", "PUSH", None),
        ("QMS-PUSH", "Quality findings and supplier escapes", "QMS", "PUSH", None),
        ("SMS-PUSH", "Safety occurrence linkage", "SMS", "PUSH", None),
        ("PROCUREMENT-PUSH", "Supplier and batch performance", "PROCUREMENT", "PUSH", None),
    ]
    source_ids: List[str] = []
    for code, name, source_type, transport, interval in source_specs:
        source = db.query(domain.ReliabilitySource).filter(
            domain.ReliabilitySource.amo_id == amo_id, domain.ReliabilitySource.code == code
        ).first()
        if not source:
            source = domain.ReliabilitySource(
                amo_id=amo_id,
                code=code,
                name=name,
                source_type=source_type,
                transport=transport,
                mapping_version="1",
                configuration_json={"canonical_contract": "reliability-event-v1"},
                poll_interval_minutes=interval,
                next_poll_at=utcnow() if transport == "INTERNAL" else None,
                created_by_user_id=actor_user_id,
            )
            db.add(source)
            db.flush()
            created["sources"] += 1
        source_ids.append(source.id)
    metric_specs = [
        ("DEFECT_RATE_100FH", "Defect rate per 100 FH", ["DEFECT", "REPEAT_DEFECT"], "FH", Decimal("100"), Decimal("50"), Decimal("3"), Decimal("5")),
        ("TECH_DELAY_100FLT", "Technical interruptions per 100 flights", ["TECHNICAL_DELAY", "TECHNICAL_CANCELLATION", "RETURN_TO_GATE", "AIR_TURNBACK", "DIVERSION"], "FLIGHTS", Decimal("100"), Decimal("30"), Decimal("2"), Decimal("4")),
        ("UNSCHED_REMOVAL_1000FH", "Unscheduled removals per 1,000 FH", ["UNSCHEDULED_REMOVAL"], "FH", Decimal("1000"), Decimal("100"), Decimal("1.5"), Decimal("3")),
        ("MEL_BURDEN_100FLT", "MEL/CDL burden per 100 flights", ["MEL_DEFERRAL", "CDL_DEFERRAL"], "FLIGHTS", Decimal("100"), Decimal("30"), Decimal("3"), Decimal("6")),
    ]
    metric_ids: List[str] = []
    for code, name, event_types, denominator, multiplier, minimum, caution, alert in metric_specs:
        metric = db.query(domain.ReliabilityMetricDefinition).filter(
            domain.ReliabilityMetricDefinition.programme_version_id == version.id,
            domain.ReliabilityMetricDefinition.code == code,
        ).first()
        if not metric:
            metric = domain.ReliabilityMetricDefinition(
                amo_id=amo_id,
                programme_version_id=version.id,
                code=code,
                name=name,
                scope_type="FLEET",
                method="RATE",
                numerator_event_types=event_types,
                denominator_type=denominator,
                multiplier=multiplier,
                window_days=30,
                schedule_interval_minutes=1440,
                minimum_exposure=minimum,
                direction="ABOVE",
                formula_version="1",
                next_run_at=utcnow(),
            )
            db.add(metric)
            db.flush()
            created["metrics"] += 1
        metric_ids.append(metric.id)
        threshold = db.query(domain.ReliabilityThresholdVersion).filter(
            domain.ReliabilityThresholdVersion.metric_definition_id == metric.id,
            domain.ReliabilityThresholdVersion.version == "INITIAL",
        ).first()
        if not threshold:
            threshold = domain.ReliabilityThresholdVersion(
                amo_id=amo_id,
                metric_definition_id=metric.id,
                version="INITIAL",
                status="DRAFT",
                caution_value=caution,
                alert_value=alert,
                minimum_exposure=minimum,
                rationale="Initial conservative threshold requiring accountable approval before activation.",
            )
            db.add(threshold)
            created["thresholds"] += 1
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="PROGRAMME",
        entity_id=programme.id,
        action="MODULE_BOOTSTRAPPED",
        payload=created,
        actor_user_id=actor_user_id,
    )
    db.commit()
    return schemas.BootstrapResult(
        programme_id=programme.id,
        programme_version_id=version.id,
        source_ids=source_ids,
        metric_ids=metric_ids,
        created=created,
    )
