from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterator, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import services as audit_services
from amodb.apps.notifications import service as notification_service
from amodb.database import WriteSessionLocal, close_session_safely, get_write_db, probe_database
from amodb.database_resilience import database_circuit, is_database_disconnect

from . import models
from .enums import QMSAuditKind, QMSAuditScheduleFrequency, QMSAuditStatus, QMSDomain
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .router import (
    _advance_schedule_date,
    _audit_metadata,
    _deserialize_external_auditees,
    _generate_audit_reference,
    _notify_user,
    _resolve_audit_scope,
    _scope_default_code_for_kind,
    _serialize_external_auditees,
    _validate_one_calendar_year,
)
from .schemas import QMSExternalAuditeeContact
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)


planner_schedule_router = APIRouter()
logger = logging.getLogger("amodb.quality.planner.automation")
_PLANNER_TIMEZONE_NAME = "Africa/Nairobi"
_PLANNER_TIMEZONE = ZoneInfo(_PLANNER_TIMEZONE_NAME)
_AUTOMATION_LOCK_KEY = 728_614_903
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_state_lock = threading.Lock()
_last_cycle_lock = threading.Lock()
_last_cycle: dict[str, Any] = {
    "started_at": None,
    "completed_at": None,
    "materialized": 0,
    "conflicts": 0,
    "upcoming_notices": 0,
    "day_of_notices": 0,
    "errors": 0,
}

_SOURCE_SPECS: dict[str, dict[str, str | None]] = {
    "CAR": {
        "table": "quality_cars",
        "start_column": "due_date",
        "end_column": None,
        "responsible_column": "assigned_to_user_id",
        "location_column": None,
        "active_predicate": "closed_at IS NULL AND UPPER(CAST(status AS TEXT)) NOT IN ('CLOSED','CANCELLED')",
    },
    "CAPA": {
        "table": "qms_corrective_actions",
        "start_column": "due_date",
        "end_column": None,
        "responsible_column": "responsible_user_id",
        "location_column": None,
        "active_predicate": "UPPER(CAST(status AS TEXT)) NOT IN ('CLOSED','REJECTED')",
    },
    "TRAINING_EVENT": {
        "table": "training_events",
        "start_column": "starts_on",
        "end_column": "ends_on",
        "responsible_column": None,
        "location_column": "location",
        "active_predicate": "UPPER(CAST(status AS TEXT)) <> 'CANCELLED'",
    },
}


class PlannerExternalAttendee(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    designation: str | None = Field(default=None, max_length=150)


class PlannerPersonOption(BaseModel):
    id: str
    full_name: str
    email: str | None = None
    role: str | None = None
    department_name: str | None = None


class PlannerScopeOption(BaseModel):
    id: str
    code: str
    name: str
    party_level: str
    default_kind: str


class PlannerScheduleOptionsResponse(BaseModel):
    timezone_name: str
    frequencies: list[str]
    kinds: list[str]
    supported_source_types: list[str]
    unsupported_source_types: dict[str, str]
    scopes: list[PlannerScopeOption]
    people: list[PlannerPersonOption]


class PlannerConflict(BaseModel):
    subject_type: str
    subject_id: str
    title: str
    start_date: date
    end_date: date
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = None
    conflicting_user_ids: list[str] = Field(default_factory=list)
    reason: str


class PlannerConflictCheckResponse(BaseModel):
    has_conflicts: bool
    conflicts: list[PlannerConflict]


class PlannerAuditScheduleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    domain: QMSDomain = QMSDomain.AMO
    kind: QMSAuditKind = QMSAuditKind.INTERNAL
    audit_scope_id: uuid.UUID | None = None
    audit_scope_code: str | None = Field(default=None, min_length=2, max_length=16)
    frequency: QMSAuditScheduleFrequency = QMSAuditScheduleFrequency.ONE_TIME
    next_due_date: date
    start_time: time = time(hour=9)
    end_time: time | None = None
    duration_days: int = Field(default=1, ge=1, le=90)
    timezone_name: str = Field(default=_PLANNER_TIMEZONE_NAME, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    scope: str | None = None
    criteria: str | None = None
    notes: str | None = None
    auditee: str | None = Field(default=None, max_length=255)
    auditee_email: EmailStr | None = None
    auditee_user_id: str | None = None
    external_auditees: list[QMSExternalAuditeeContact] = Field(default_factory=list)
    lead_auditor_user_id: str | None = None
    observer_auditor_user_id: str | None = None
    assistant_auditor_user_id: str | None = None
    attendee_user_ids: list[str] = Field(default_factory=list)
    external_attendees: list[PlannerExternalAttendee] = Field(default_factory=list)
    notify_auditors: bool = True
    notify_auditees: bool = True
    notify_attendees: bool = True
    reminder_interval_days: int = Field(default=7, ge=1, le=60)
    automation_active: bool = True
    allow_conflicts: bool = False
    conflict_override_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_timing(self) -> "PlannerAuditScheduleCreate":
        _validate_timing(self.timezone_name, self.start_time, self.end_time)
        self.attendee_user_ids = _dedupe(self.attendee_user_ids)
        _validate_conflict_override(self.allow_conflicts, self.conflict_override_reason)
        return self


class PlannerAuditScheduleUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    next_due_date: date
    start_time: time
    end_time: time | None = None
    duration_days: int = Field(default=1, ge=1, le=90)
    timezone_name: str = Field(default=_PLANNER_TIMEZONE_NAME, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    attendee_user_ids: list[str] = Field(default_factory=list)
    external_attendees: list[PlannerExternalAttendee] = Field(default_factory=list)
    notify_attendees: bool = True
    reason: str = Field(min_length=8, max_length=1000)
    allow_conflicts: bool = False
    conflict_override_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_timing(self) -> "PlannerAuditScheduleUpdate":
        _validate_timing(self.timezone_name, self.start_time, self.end_time)
        self.attendee_user_ids = _dedupe(self.attendee_user_ids)
        _validate_conflict_override(self.allow_conflicts, self.conflict_override_reason)
        return self


class PlannerAuditScheduleStateUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=8, max_length=1000)


class PlannerSourceMetadataUpsert(BaseModel):
    source_type: Literal["CAR", "CAPA", "TRAINING_EVENT", "MANAGEMENT_REVIEW"]
    source_id: str = Field(min_length=1, max_length=64)
    start_date: date
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    timezone_name: str = Field(default=_PLANNER_TIMEZONE_NAME, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    responsible_user_id: str | None = None
    attendee_user_ids: list[str] = Field(default_factory=list)
    external_attendees: list[PlannerExternalAttendee] = Field(default_factory=list)
    notify_attendees: bool = True
    notes: str | None = None
    expected_version: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=8, max_length=1000)
    allow_conflicts: bool = False
    conflict_override_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_timing(self) -> "PlannerSourceMetadataUpsert":
        _validate_timing(self.timezone_name, self.start_time, self.end_time)
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date.")
        self.attendee_user_ids = _dedupe(self.attendee_user_ids)
        _validate_conflict_override(self.allow_conflicts, self.conflict_override_reason)
        return self


class PlannerSourceMetadataResponse(BaseModel):
    source_type: str
    source_id: str
    start_date: date
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    timezone_name: str
    location: str | None = None
    responsible_user_id: str | None = None
    attendee_user_ids: list[str] = Field(default_factory=list)
    external_attendees: list[dict[str, Any]] = Field(default_factory=list)
    notify_attendees: bool
    lifecycle_status: str
    version: int
    conflicts: list[PlannerConflict] = Field(default_factory=list)


class PlannerAuditScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    amo_id: str
    title: str
    domain: str
    kind: str
    audit_scope_id: str | None = None
    audit_scope_code: str | None = None
    frequency: str
    next_due_date: date
    start_time: time | None = None
    end_time: time | None = None
    duration_days: int
    timezone_name: str
    location: str | None = None
    scope: str | None = None
    criteria: str | None = None
    notes: str | None = None
    auditee: str | None = None
    auditee_email: str | None = None
    auditee_user_id: str | None = None
    external_auditees: list[dict[str, Any]] = Field(default_factory=list)
    lead_auditor_user_id: str | None = None
    observer_auditor_user_id: str | None = None
    assistant_auditor_user_id: str | None = None
    attendee_user_ids: list[str] = Field(default_factory=list)
    external_attendees: list[dict[str, Any]] = Field(default_factory=list)
    notify_auditors: bool
    notify_auditees: bool
    notify_attendees: bool
    reminder_interval_days: int
    automation_active: bool
    lifecycle_status: str
    version: int
    created_at: datetime
    notifications_queued: int = 0
    conflicts: list[PlannerConflict] = Field(default_factory=list)


class PlannerAutomationStatusResponse(BaseModel):
    enabled: bool
    running: bool
    interval_seconds: int
    materialize_lead_days: int
    timezone_name: str
    last_cycle: dict[str, Any]


@dataclass(slots=True)
class _Candidate:
    subject_type: str
    subject_id: str
    title: str
    start_date: date
    end_date: date
    start_time: time | None
    end_time: time | None
    location: str | None
    user_ids: set[str]


def _validate_timing(timezone_name: str, start_time: time | None, end_time: time | None) -> None:
    if timezone_name != _PLANNER_TIMEZONE_NAME:
        raise ValueError("Quality planner schedules currently use the tenant timezone Africa/Nairobi.")
    if start_time and end_time and end_time <= start_time:
        raise ValueError("End time must be later than start time.")
    if end_time and not start_time:
        raise ValueError("A start time is required when an end time is supplied.")


def _validate_conflict_override(allow_conflicts: bool, reason: str | None) -> None:
    if allow_conflicts and len((reason or "").strip()) < 8:
        raise ValueError("A conflict override reason of at least 8 characters is required.")


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _automation_enabled() -> bool:
    return (os.getenv("QUALITY_PLANNER_SCHEDULER_ENABLED") or "true").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _interval_seconds() -> int:
    try:
        return max(int(os.getenv("QUALITY_PLANNER_SCHEDULER_INTERVAL_SEC", "300")), 60)
    except ValueError:
        return 300


def _materialize_lead_days() -> int:
    try:
        return max(0, min(int(os.getenv("QUALITY_PLANNER_MATERIALIZE_LEAD_DAYS", "14")), 90))
    except ValueError:
        return 14


def _max_catchup_occurrences() -> int:
    try:
        return max(1, min(int(os.getenv("QUALITY_PLANNER_MAX_CATCHUP_OCCURRENCES", "12")), 60))
    except ValueError:
        return 12


def _json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _dump_json_list(value: list[Any]) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _normalise_location(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def _user_display_name(user: account_models.User | None) -> str:
    if user is None:
        return ""
    return (
        str(getattr(user, "full_name", "") or "").strip()
        or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        or str(getattr(user, "email", "") or "").strip()
        or str(getattr(user, "id", ""))
    )


def _validate_people(db: Session, *, amo_id: str, user_ids: list[str]) -> dict[str, account_models.User]:
    selected = _dedupe(user_ids)
    if not selected:
        return {}
    users = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.id.in_(selected),
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .all()
    )
    by_id = {str(user.id): user for user in users}
    missing = [user_id for user_id in selected if user_id not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "One or more selected participants are inactive, belong to another tenant, or no longer exist.",
                "invalid_user_ids": missing,
            },
        )
    return by_id


def _metadata_for_schedule(db: Session, *, amo_id: str, schedule_id: uuid.UUID, lock: bool = False) -> QMSPlannerScheduleMetadata | None:
    query = db.query(QMSPlannerScheduleMetadata).filter(
        QMSPlannerScheduleMetadata.amo_id == amo_id,
        QMSPlannerScheduleMetadata.schedule_id == schedule_id,
    )
    return query.with_for_update().first() if lock else query.first()


def _metadata_for_audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> QMSPlannerScheduleMetadata | None:
    return db.query(QMSPlannerScheduleMetadata).filter(
        QMSPlannerScheduleMetadata.amo_id == amo_id,
        QMSPlannerScheduleMetadata.audit_id == audit_id,
    ).first()


def _metadata_for_source(db: Session, *, amo_id: str, source_type: str, source_id: str, lock: bool = False) -> QMSPlannerScheduleMetadata | None:
    query = db.query(QMSPlannerScheduleMetadata).filter(
        QMSPlannerScheduleMetadata.amo_id == amo_id,
        QMSPlannerScheduleMetadata.source_type == source_type,
        QMSPlannerScheduleMetadata.source_id == source_id,
    )
    return query.with_for_update().first() if lock else query.first()


def _schedule_user_ids(schedule: models.QMSAuditSchedule, metadata: QMSPlannerScheduleMetadata | None) -> set[str]:
    return {
        str(value)
        for value in [
            schedule.lead_auditor_user_id,
            schedule.observer_auditor_user_id,
            schedule.assistant_auditor_user_id,
            schedule.auditee_user_id,
            *(_json_list(metadata.attendee_user_ids_json) if metadata else []),
        ]
        if value
    }


def _audit_user_ids(audit: models.QMSAudit, metadata: QMSPlannerScheduleMetadata | None) -> set[str]:
    return {
        str(value)
        for value in [
            audit.lead_auditor_user_id,
            audit.observer_auditor_user_id,
            audit.assistant_auditor_user_id,
            audit.auditee_user_id,
            *(_json_list(metadata.attendee_user_ids_json) if metadata else []),
        ]
        if value
    }


def _time_bounds(start_value: time | None, end_value: time | None) -> tuple[time, time]:
    return start_value or time.min, end_value or time.max


def _overlaps(left: _Candidate, right: _Candidate) -> bool:
    if left.end_date < right.start_date or right.end_date < left.start_date:
        return False
    if left.start_date != left.end_date or right.start_date != right.end_date:
        return True
    left_start, left_end = _time_bounds(left.start_time, left.end_time)
    right_start, right_end = _time_bounds(right.start_time, right.end_time)
    return left_start < right_end and right_start < left_end


def _candidate_conflict(candidate: _Candidate, existing: _Candidate) -> PlannerConflict | None:
    if not _overlaps(candidate, existing):
        return None
    shared_users = sorted(candidate.user_ids.intersection(existing.user_ids))
    same_location = bool(
        _normalise_location(candidate.location)
        and _normalise_location(candidate.location) == _normalise_location(existing.location)
    )
    if not shared_users and not same_location:
        return None
    if shared_users and same_location:
        reason = "Responsible personnel/attendees and location overlap."
    elif shared_users:
        reason = "Responsible personnel or attendees overlap."
    else:
        reason = "Location overlaps another active Quality commitment."
    return PlannerConflict(
        subject_type=existing.subject_type,
        subject_id=existing.subject_id,
        title=existing.title,
        start_date=existing.start_date,
        end_date=existing.end_date,
        start_time=existing.start_time,
        end_time=existing.end_time,
        location=existing.location,
        conflicting_user_ids=shared_users,
        reason=reason,
    )


def _collect_conflicts(
    db: Session,
    *,
    amo_id: str,
    candidate: _Candidate,
    exclude_schedule_id: str | None = None,
    exclude_audit_id: str | None = None,
    exclude_source: tuple[str, str] | None = None,
) -> list[PlannerConflict]:
    window_start = candidate.start_date - timedelta(days=90)
    window_end = candidate.end_date + timedelta(days=90)
    existing: list[_Candidate] = []

    schedule_rows = (
        db.query(models.QMSAuditSchedule, QMSPlannerScheduleMetadata)
        .join(QMSPlannerScheduleMetadata, QMSPlannerScheduleMetadata.schedule_id == models.QMSAuditSchedule.id)
        .filter(
            models.QMSAuditSchedule.amo_id == amo_id,
            models.QMSAuditSchedule.is_active.is_(True),
            models.QMSAuditSchedule.deleted_at.is_(None),
            models.QMSAuditSchedule.next_due_date >= window_start,
            models.QMSAuditSchedule.next_due_date <= window_end,
            QMSPlannerScheduleMetadata.lifecycle_status == "ACTIVE",
        )
        .limit(1000)
        .all()
    )
    for schedule, metadata in schedule_rows:
        if exclude_schedule_id and str(schedule.id) == exclude_schedule_id:
            continue
        existing.append(_Candidate(
            subject_type="AUDIT_SCHEDULE",
            subject_id=str(schedule.id),
            title=schedule.title,
            start_date=schedule.next_due_date,
            end_date=schedule.next_due_date + timedelta(days=max(int(schedule.duration_days or 1), 1) - 1),
            start_time=metadata.start_time,
            end_time=metadata.end_time,
            location=metadata.location,
            user_ids=_schedule_user_ids(schedule, metadata),
        ))

    audit_rows = (
        db.query(models.QMSAudit, QMSPlannerScheduleMetadata)
        .join(QMSPlannerScheduleMetadata, QMSPlannerScheduleMetadata.audit_id == models.QMSAudit.id)
        .filter(
            models.QMSAudit.amo_id == amo_id,
            models.QMSAudit.deleted_at.is_(None),
            models.QMSAudit.status.notin_([QMSAuditStatus.CLOSED]),
            models.QMSAudit.planned_start.is_not(None),
            models.QMSAudit.planned_start >= window_start,
            models.QMSAudit.planned_start <= window_end,
            QMSPlannerScheduleMetadata.lifecycle_status == "ACTIVE",
        )
        .limit(1000)
        .all()
    )
    for audit, metadata in audit_rows:
        if exclude_audit_id and str(audit.id) == exclude_audit_id:
            continue
        existing.append(_Candidate(
            subject_type="AUDIT",
            subject_id=str(audit.id),
            title=f"{audit.audit_ref} · {audit.title}",
            start_date=audit.planned_start,
            end_date=audit.planned_end or audit.planned_start,
            start_time=metadata.start_time,
            end_time=metadata.end_time,
            location=metadata.location,
            user_ids=_audit_user_ids(audit, metadata),
        ))

    source_rows = (
        db.query(QMSPlannerScheduleMetadata)
        .filter(
            QMSPlannerScheduleMetadata.amo_id == amo_id,
            QMSPlannerScheduleMetadata.source_type.is_not(None),
            QMSPlannerScheduleMetadata.occurrence_date.is_not(None),
            QMSPlannerScheduleMetadata.occurrence_date >= window_start,
            QMSPlannerScheduleMetadata.occurrence_date <= window_end,
            QMSPlannerScheduleMetadata.lifecycle_status == "ACTIVE",
        )
        .limit(1000)
        .all()
    )
    for metadata in source_rows:
        source_key = (str(metadata.source_type), str(metadata.source_id))
        if exclude_source and source_key == exclude_source:
            continue
        existing.append(_Candidate(
            subject_type=str(metadata.source_type),
            subject_id=str(metadata.source_id),
            title=f"{metadata.source_type.replace('_', ' ').title()} commitment",
            start_date=metadata.occurrence_date,
            end_date=metadata.end_date or metadata.occurrence_date,
            start_time=metadata.start_time,
            end_time=metadata.end_time,
            location=metadata.location,
            user_ids={
                str(value)
                for value in [metadata.responsible_user_id, *_json_list(metadata.attendee_user_ids_json)]
                if value
            },
        ))

    conflicts = [conflict for item in existing if (conflict := _candidate_conflict(candidate, item))]
    conflicts.sort(key=lambda item: (item.start_date, item.start_time or time.min, item.title, item.subject_id))
    return conflicts


def _enforce_conflicts(conflicts: list[PlannerConflict], *, allow: bool) -> None:
    if conflicts and not allow:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "The proposed Quality commitment conflicts with active personnel or location allocations.",
                "conflicts": [item.model_dump(mode="json") for item in conflicts],
            },
        )


def _assert_version(metadata: QMSPlannerScheduleMetadata, expected_version: int) -> None:
    if int(metadata.version or 1) != int(expected_version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This schedule changed after it was loaded. Refresh and review the latest version.",
                "expected_version": expected_version,
                "current_version": int(metadata.version or 1),
            },
        )


def _schedule_response(
    schedule: models.QMSAuditSchedule,
    metadata: QMSPlannerScheduleMetadata,
    *,
    notifications_queued: int = 0,
    conflicts: list[PlannerConflict] | None = None,
) -> PlannerAuditScheduleResponse:
    return PlannerAuditScheduleResponse(
        id=str(schedule.id),
        amo_id=str(schedule.amo_id),
        title=schedule.title,
        domain=_enum_value(schedule.domain),
        kind=_enum_value(schedule.kind),
        audit_scope_id=str(schedule.audit_scope_id) if schedule.audit_scope_id else None,
        audit_scope_code=schedule.audit_scope_code,
        frequency=_enum_value(schedule.frequency),
        next_due_date=schedule.next_due_date,
        start_time=metadata.start_time,
        end_time=metadata.end_time,
        duration_days=schedule.duration_days,
        timezone_name=metadata.timezone_name,
        location=metadata.location,
        scope=schedule.scope,
        criteria=schedule.criteria,
        notes=metadata.notes,
        auditee=schedule.auditee,
        auditee_email=schedule.auditee_email,
        auditee_user_id=schedule.auditee_user_id,
        external_auditees=_deserialize_external_auditees(schedule.external_auditees_json),
        lead_auditor_user_id=schedule.lead_auditor_user_id,
        observer_auditor_user_id=schedule.observer_auditor_user_id,
        assistant_auditor_user_id=schedule.assistant_auditor_user_id,
        attendee_user_ids=[str(item) for item in _json_list(metadata.attendee_user_ids_json)],
        external_attendees=[dict(item) for item in _json_list(metadata.external_attendees_json) if isinstance(item, dict)],
        notify_auditors=bool(schedule.notify_auditors),
        notify_auditees=bool(schedule.notify_auditees),
        notify_attendees=bool(metadata.notify_attendees),
        reminder_interval_days=schedule.reminder_interval_days,
        automation_active=bool(schedule.is_active),
        lifecycle_status=metadata.lifecycle_status,
        version=int(metadata.version or 1),
        created_at=schedule.created_at,
        notifications_queued=notifications_queued,
        conflicts=conflicts or [],
    )


def _recipient_targets(
    db: Session,
    *,
    amo_id: str,
    role_user_ids: list[tuple[str, str | None]],
    external_recipients: list[tuple[str, str, str]],
) -> list[dict[str, str | None]]:
    user_ids = _dedupe([user_id for _, user_id in role_user_ids if user_id])
    users = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.id.in_(user_ids),
            account_models.User.is_active.is_(True),
        )
        .all()
        if user_ids else []
    )
    users_by_id = {str(user.id): user for user in users}
    recipients: list[dict[str, str | None]] = []
    seen: set[tuple[str | None, str | None]] = set()

    def add(role: str, user_id: str | None, email: str | None, label: str | None) -> None:
        user = users_by_id.get(str(user_id)) if user_id else None
        resolved_user_id = str(user.id) if user else None
        resolved_email = str(getattr(user, "email", "") or email or "").strip() or None
        key = (resolved_user_id, resolved_email.lower() if resolved_email else None)
        if key in seen:
            return
        seen.add(key)
        recipients.append({
            "role": role,
            "user_id": resolved_user_id,
            "email": resolved_email,
            "label": _user_display_name(user) or label or resolved_email or role,
        })

    for role, user_id in role_user_ids:
        add(role, user_id, None, None)
    for role, email, label in external_recipients:
        if email:
            add(role, None, email, label)
    return recipients


def _schedule_recipients(db: Session, schedule: models.QMSAuditSchedule, metadata: QMSPlannerScheduleMetadata) -> list[dict[str, str | None]]:
    role_user_ids: list[tuple[str, str | None]] = []
    if schedule.notify_auditors:
        role_user_ids.extend([
            ("lead_auditor", schedule.lead_auditor_user_id),
            ("observer_auditor", schedule.observer_auditor_user_id),
            ("assistant_auditor", schedule.assistant_auditor_user_id),
        ])
    if schedule.notify_auditees:
        role_user_ids.append(("auditee", schedule.auditee_user_id))
    if metadata.notify_attendees:
        role_user_ids.extend(("attendee", str(item)) for item in _json_list(metadata.attendee_user_ids_json))

    external: list[tuple[str, str, str]] = []
    if schedule.notify_auditees:
        if schedule.auditee_email:
            external.append(("auditee_external", schedule.auditee_email, schedule.auditee or schedule.auditee_email))
        for item in _deserialize_external_auditees(schedule.external_auditees_json):
            external.append((
                "auditee_external",
                str(item.get("email") or ""),
                f"{item.get('first_name', '')} {item.get('last_name', '')}".strip() or str(item.get("designation") or "External auditee"),
            ))
    if metadata.notify_attendees:
        for item in _json_list(metadata.external_attendees_json):
            if isinstance(item, dict):
                external.append((
                    "attendee_external",
                    str(item.get("email") or ""),
                    str(item.get("name") or item.get("designation") or item.get("email") or "External attendee"),
                ))
    return _recipient_targets(db, amo_id=str(schedule.amo_id), role_user_ids=role_user_ids, external_recipients=external)


def _send_notifications(
    db: Session,
    *,
    amo_id: str,
    recipients: list[dict[str, str | None]],
    template_key: str,
    subject: str,
    message: str,
    context: dict[str, Any],
    correlation_seed: str,
    action_required: bool,
) -> int:
    queued = 0
    severity = models.QMSNotificationSeverity.ACTION_REQUIRED if action_required else models.QMSNotificationSeverity.INFO
    for recipient in recipients:
        user_id = recipient.get("user_id")
        email = recipient.get("email")
        role = recipient.get("role") or "recipient"
        if user_id:
            _notify_user(db, user_id, message, severity)
            queued += 1
        if email:
            notification_service.send_email(
                template_key=template_key,
                recipient=email,
                subject=subject,
                context={**context, "recipient_role": role, "recipient_label": recipient.get("label")},
                correlation_id=f"{correlation_seed}:{role}:{user_id or email.lower()}",
                critical=True,
                email_class="CRITICAL",
                amo_id=amo_id,
                db=db,
                recipient_user_id=user_id,
                audit_context={"purpose": "qms-planner-notice", "template_key": template_key},
            )
            queued += 1
    return queued


def _notify_schedule_change(
    db: Session,
    *,
    schedule: models.QMSAuditSchedule,
    metadata: QMSPlannerScheduleMetadata,
    state: str,
    reason: str,
) -> int:
    time_label = metadata.start_time.strftime("%H:%M") if metadata.start_time else "All day"
    return _send_notifications(
        db,
        amo_id=str(schedule.amo_id),
        recipients=_schedule_recipients(db, schedule, metadata),
        template_key=f"qms_planner_schedule_{state}",
        subject=f"Quality schedule {state.replace('_', ' ')} · {schedule.title}",
        message=(
            f"Quality schedule {schedule.title} was {state.replace('_', ' ')} for "
            f"{schedule.next_due_date.isoformat()} at {time_label} {_PLANNER_TIMEZONE_NAME}. Reason: {reason}"
        ),
        context={
            "schedule_id": str(schedule.id),
            "title": schedule.title,
            "state": state,
            "reason": reason,
            "next_due_date": schedule.next_due_date.isoformat(),
            "start_time": time_label,
            "end_time": metadata.end_time.strftime("%H:%M") if metadata.end_time else None,
            "location": metadata.location,
            "version": metadata.version,
        },
        correlation_seed=f"planner-schedule-{state}:{schedule.id}:{metadata.version}",
        action_required=state in {"suspended", "conflict_blocked"},
    )


def _accountable_actor_id(db: Session, schedule: models.QMSAuditSchedule) -> str | None:
    if schedule.created_by_user_id:
        creator = db.query(account_models.User).filter(
            account_models.User.id == schedule.created_by_user_id,
            account_models.User.amo_id == schedule.amo_id,
            account_models.User.is_active.is_(True),
        ).first()
        if creator:
            return str(creator.id)
    manager = db.query(account_models.User).filter(
        account_models.User.amo_id == schedule.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.role.in_([
            account_models.AccountRole.QUALITY_MANAGER,
            account_models.AccountRole.AMO_ADMIN,
        ]),
    ).order_by(account_models.User.role.asc(), account_models.User.id.asc()).first()
    return str(manager.id) if manager else None


def _materialize_occurrence(
    db: Session,
    *,
    schedule: models.QMSAuditSchedule,
    actor_user_id: str | None,
) -> tuple[models.QMSAudit | None, bool]:
    occurrence_date = schedule.next_due_date
    template = _metadata_for_schedule(db, amo_id=str(schedule.amo_id), schedule_id=schedule.id, lock=True)
    if template is None or template.lifecycle_status != "ACTIVE":
        return None, True

    planned_end = occurrence_date + timedelta(days=max(int(schedule.duration_days or 1), 1) - 1)
    candidate = _Candidate(
        subject_type="AUDIT_OCCURRENCE",
        subject_id=f"{schedule.id}:{occurrence_date.isoformat()}",
        title=schedule.title,
        start_date=occurrence_date,
        end_date=planned_end,
        start_time=template.start_time,
        end_time=template.end_time,
        location=template.location,
        user_ids=_schedule_user_ids(schedule, template),
    )
    conflicts = _collect_conflicts(
        db,
        amo_id=str(schedule.amo_id),
        candidate=candidate,
        exclude_schedule_id=str(schedule.id),
    )
    if conflicts:
        audit_services.log_event(
            db,
            amo_id=str(schedule.amo_id),
            actor_user_id=actor_user_id,
            entity_type="qms_audit_schedule",
            entity_id=str(schedule.id),
            action="auto_run_blocked_by_conflict",
            after={"occurrence_date": occurrence_date.isoformat(), "conflicts": [item.model_dump(mode="json") for item in conflicts]},
            correlation_id=f"qms-planner-conflict:{schedule.id}:{occurrence_date.isoformat()}",
            metadata={"automation": True, "scheduler": "quality-planner"},
            critical=True,
        )
        _notify_schedule_change(
            db,
            schedule=schedule,
            metadata=template,
            state="conflict_blocked",
            reason="Automatic occurrence creation was blocked by a personnel or location conflict.",
        )
        return None, True

    existing_metadata = db.query(QMSPlannerScheduleMetadata).filter(
        QMSPlannerScheduleMetadata.amo_id == schedule.amo_id,
        QMSPlannerScheduleMetadata.source_schedule_id == schedule.id,
        QMSPlannerScheduleMetadata.occurrence_date == occurrence_date,
    ).first()
    if existing_metadata and existing_metadata.audit_id:
        return None, False

    _validate_one_calendar_year(start=occurrence_date, end=planned_end)
    audit_scope_code = schedule.audit_scope_code or _scope_default_code_for_kind(schedule.kind)
    audit_ref, unit_code, ref_year, ref_sequence = _generate_audit_reference(
        db,
        amo_id=str(schedule.amo_id),
        target_date=occurrence_date,
        audit_scope_code=audit_scope_code,
    )
    audit = models.QMSAudit(
        amo_id=schedule.amo_id,
        domain=schedule.domain,
        kind=schedule.kind,
        audit_ref=audit_ref,
        audit_scope_id=schedule.audit_scope_id,
        audit_scope_code=audit_scope_code,
        reference_family="QAR",
        unit_code=unit_code,
        ref_year=ref_year,
        ref_sequence=ref_sequence,
        title=schedule.title,
        scope=schedule.scope,
        criteria=schedule.criteria,
        auditee=schedule.auditee,
        auditee_email=schedule.auditee_email,
        auditee_user_id=schedule.auditee_user_id,
        external_auditees_json=schedule.external_auditees_json,
        lead_auditor_user_id=schedule.lead_auditor_user_id,
        observer_auditor_user_id=schedule.observer_auditor_user_id,
        assistant_auditor_user_id=schedule.assistant_auditor_user_id,
        notify_auditors=schedule.notify_auditors,
        notify_auditees=schedule.notify_auditees,
        reminder_interval_days=schedule.reminder_interval_days,
        planned_start=occurrence_date,
        planned_end=planned_end,
        created_by_user_id=actor_user_id,
    )
    db.add(audit)
    db.flush()
    occurrence_metadata = QMSPlannerScheduleMetadata(
        amo_id=str(schedule.amo_id),
        audit_id=audit.id,
        source_schedule_id=schedule.id,
        occurrence_date=occurrence_date,
        end_date=planned_end,
        start_time=template.start_time,
        end_time=template.end_time,
        timezone_name=template.timezone_name,
        location=template.location,
        notes=template.notes,
        responsible_user_id=schedule.lead_auditor_user_id,
        attendee_user_ids_json=template.attendee_user_ids_json,
        external_attendees_json=template.external_attendees_json,
        notify_attendees=template.notify_attendees,
        lifecycle_status="ACTIVE",
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(occurrence_metadata)
    db.flush()

    schedule.last_run_at = datetime.now(timezone.utc)
    if schedule.frequency == QMSAuditScheduleFrequency.ONE_TIME:
        schedule.is_active = False
        template.lifecycle_status = "COMPLETED"
    else:
        schedule.next_due_date = _advance_schedule_date(schedule, occurrence_date)
    template.version = int(template.version or 1) + 1
    template.updated_by_user_id = actor_user_id

    audit_services.log_event(
        db,
        amo_id=str(schedule.amo_id),
        actor_user_id=actor_user_id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="auto_create_from_schedule",
        after={
            "audit_ref": audit.audit_ref,
            "source_schedule_id": str(schedule.id),
            "occurrence_date": occurrence_date.isoformat(),
            "planned_end": planned_end.isoformat(),
        },
        correlation_id=f"qms-planner-occurrence:{schedule.id}:{occurrence_date.isoformat()}",
        metadata={"automation": True, "scheduler": "quality-planner"},
        critical=True,
    )
    _send_notifications(
        db,
        amo_id=str(schedule.amo_id),
        recipients=_schedule_recipients(db, schedule, occurrence_metadata),
        template_key="qms_planner_audit_materialized",
        subject=f"Audit scheduled · {audit.audit_ref}",
        message=f"Audit {audit.audit_ref} ({audit.title}) is scheduled for {occurrence_date.isoformat()}.",
        context={
            "audit_id": str(audit.id),
            "audit_ref": audit.audit_ref,
            "title": audit.title,
            "planned_start": occurrence_date.isoformat(),
            "planned_end": planned_end.isoformat(),
            "location": occurrence_metadata.location,
        },
        correlation_seed=f"qms-planner-audit-created:{audit.id}",
        action_required=True,
    )
    return audit, False


def _run_audit_reminders(db: Session, *, today: date) -> tuple[int, int]:
    horizon = today + timedelta(days=90)
    audits = db.query(models.QMSAudit).filter(
        models.QMSAudit.status == QMSAuditStatus.PLANNED,
        models.QMSAudit.planned_start.is_not(None),
        models.QMSAudit.planned_start >= today,
        models.QMSAudit.planned_start <= horizon,
        models.QMSAudit.deleted_at.is_(None),
    ).order_by(models.QMSAudit.amo_id.asc(), models.QMSAudit.planned_start.asc()).all()
    upcoming = 0
    day_of = 0
    now = datetime.now(timezone.utc)
    for audit in audits:
        metadata = _metadata_for_audit(db, amo_id=str(audit.amo_id), audit_id=audit.id)
        if metadata is None or metadata.lifecycle_status != "ACTIVE":
            continue
        schedule_stub = models.QMSAuditSchedule(
            amo_id=audit.amo_id,
            title=audit.title,
            next_due_date=audit.planned_start,
            lead_auditor_user_id=audit.lead_auditor_user_id,
            observer_auditor_user_id=audit.observer_auditor_user_id,
            assistant_auditor_user_id=audit.assistant_auditor_user_id,
            auditee_user_id=audit.auditee_user_id,
            auditee=audit.auditee,
            auditee_email=audit.auditee_email,
            external_auditees_json=audit.external_auditees_json,
            notify_auditors=audit.notify_auditors,
            notify_auditees=audit.notify_auditees,
        )
        recipients = _schedule_recipients(db, schedule_stub, metadata)
        if audit.planned_start == today:
            if audit.day_of_notice_sent_at and audit.day_of_notice_sent_at.astimezone(_PLANNER_TIMEZONE).date() == today:
                continue
            _send_notifications(
                db,
                amo_id=str(audit.amo_id),
                recipients=recipients,
                template_key="qms_planner_audit_day_of",
                subject=f"Audit today · {audit.audit_ref}",
                message=f"Audit {audit.audit_ref} ({audit.title}) is scheduled for today.",
                context={"audit_id": str(audit.id), "audit_ref": audit.audit_ref, "location": metadata.location},
                correlation_seed=f"qms-planner-day-of:{audit.id}:{today.isoformat()}",
                action_required=True,
            )
            audit.day_of_notice_sent_at = now
            day_of += 1
            continue
        days_until = (audit.planned_start - today).days
        reminder_window = max(1, min(int(audit.reminder_interval_days or 7), 60))
        if days_until <= reminder_window and audit.upcoming_notice_sent_at is None:
            _send_notifications(
                db,
                amo_id=str(audit.amo_id),
                recipients=recipients,
                template_key="qms_planner_audit_upcoming",
                subject=f"Upcoming audit · {audit.audit_ref}",
                message=f"Audit {audit.audit_ref} ({audit.title}) is scheduled for {audit.planned_start.isoformat()}.",
                context={"audit_id": str(audit.id), "audit_ref": audit.audit_ref, "days_until": days_until, "location": metadata.location},
                correlation_seed=f"qms-planner-upcoming:{audit.id}:{audit.planned_start.isoformat()}",
                action_required=False,
            )
            audit.upcoming_notice_sent_at = now
            upcoming += 1
    return upcoming, day_of


@contextmanager
def _advisory_lock(db: Session) -> Iterator[bool]:
    if db.get_bind().dialect.name != "postgresql":
        yield True
        return
    acquired = bool(db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _AUTOMATION_LOCK_KEY}).scalar())
    try:
        yield acquired
    finally:
        if acquired:
            try:
                db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _AUTOMATION_LOCK_KEY})
            except Exception:
                logger.debug("Quality planner advisory unlock failed", exc_info=True)


def run_quality_planner_cycle() -> dict[str, Any]:
    result: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "materialized": 0,
        "conflicts": 0,
        "upcoming_notices": 0,
        "day_of_notices": 0,
        "errors": 0,
    }
    db = WriteSessionLocal()
    try:
        with _advisory_lock(db) as acquired:
            if not acquired:
                result["completed_at"] = datetime.now(timezone.utc).isoformat()
                return result
            today = datetime.now(_PLANNER_TIMEZONE).date()
            horizon = today + timedelta(days=_materialize_lead_days())
            schedule_ids = [row[0] for row in db.query(models.QMSAuditSchedule.id).filter(
                models.QMSAuditSchedule.is_active.is_(True),
                models.QMSAuditSchedule.next_due_date <= horizon,
                models.QMSAuditSchedule.deleted_at.is_(None),
            ).order_by(models.QMSAuditSchedule.next_due_date.asc()).all()]
            for schedule_id in schedule_ids:
                try:
                    schedule = db.query(models.QMSAuditSchedule).filter(
                        models.QMSAuditSchedule.id == schedule_id,
                        models.QMSAuditSchedule.is_active.is_(True),
                        models.QMSAuditSchedule.deleted_at.is_(None),
                    ).with_for_update(skip_locked=True).first()
                    if schedule is None:
                        db.rollback()
                        continue
                    set_postgres_tenant_context(
                        db,
                        amo_id=str(schedule.amo_id),
                        user_id=str(schedule.created_by_user_id or "quality-planner-automation"),
                    )
                    actor_user_id = _accountable_actor_id(db, schedule)
                    occurrence_count = 0
                    while schedule.is_active and schedule.next_due_date <= horizon and occurrence_count < _max_catchup_occurrences():
                        audit, blocked = _materialize_occurrence(db, schedule=schedule, actor_user_id=actor_user_id)
                        occurrence_count += 1
                        if blocked:
                            result["conflicts"] += 1
                            break
                        if audit is not None:
                            result["materialized"] += 1
                        elif schedule.frequency == QMSAuditScheduleFrequency.ONE_TIME:
                            schedule.is_active = False
                        else:
                            schedule.next_due_date = _advance_schedule_date(schedule, schedule.next_due_date)
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    logger.info("Quality planner occurrence already materialized schedule_id=%s", schedule_id)
                except Exception:
                    db.rollback()
                    result["errors"] += 1
                    logger.exception("Quality planner schedule materialization failed schedule_id=%s", schedule_id)
            try:
                upcoming, day_of = _run_audit_reminders(db, today=today)
                result["upcoming_notices"] = upcoming
                result["day_of_notices"] = day_of
                db.commit()
            except Exception:
                db.rollback()
                result["errors"] += 1
                logger.exception("Quality planner automatic reminder cycle failed")
    finally:
        close_session_safely(db)
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    with _last_cycle_lock:
        _last_cycle.clear()
        _last_cycle.update(result)
    return result


def _worker() -> None:
    while not _stop_event.is_set():
        if not probe_database():
            _stop_event.wait(database_circuit.retry_after_seconds())
            continue
        try:
            logger.info("Quality planner automation cycle completed: %s", run_quality_planner_cycle())
        except Exception as exc:
            if is_database_disconnect(exc):
                database_circuit.mark_failure(exc)
                _stop_event.wait(database_circuit.retry_after_seconds())
                continue
            logger.exception("Quality planner automation cycle failed")
        _stop_event.wait(_interval_seconds())


def start_quality_planner_scheduler() -> None:
    global _thread
    if not _automation_enabled():
        logger.info("Quality planner scheduler is suspended by configuration")
        return
    with _state_lock:
        if _thread and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(target=_worker, name="quality-planner-scheduler", daemon=True)
        _thread.start()


def stop_quality_planner_scheduler() -> None:
    global _thread
    with _state_lock:
        thread = _thread
        _stop_event.set()
        _thread = None
    if thread and thread.is_alive():
        thread.join(timeout=5)


@planner_schedule_router.get("/integrations/calendar/schedule-options", response_model=PlannerScheduleOptionsResponse)
def planner_schedule_options(
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerScheduleOptionsResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    scopes = db.query(models.QMSAuditScope).filter(
        models.QMSAuditScope.amo_id == ctx.amo_id,
        models.QMSAuditScope.is_active.is_(True),
    ).order_by(models.QMSAuditScope.sort_order.asc(), models.QMSAuditScope.name.asc()).all()
    people = db.query(account_models.User, account_models.Department.name).outerjoin(
        account_models.Department, account_models.Department.id == account_models.User.department_id
    ).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(account_models.User.full_name.asc(), account_models.User.email.asc()).limit(1000).all()
    return PlannerScheduleOptionsResponse(
        timezone_name=_PLANNER_TIMEZONE_NAME,
        frequencies=[item.value for item in QMSAuditScheduleFrequency],
        kinds=[item.value for item in QMSAuditKind],
        supported_source_types=sorted(_SOURCE_SPECS),
        unsupported_source_types={
            "MANAGEMENT_REVIEW": "The repository has no authoritative writable management-review domain record. The planner will not create a parallel lifecycle table.",
        },
        scopes=[PlannerScopeOption(
            id=str(scope.id), code=scope.code, name=scope.name,
            party_level=scope.party_level, default_kind=_enum_value(scope.default_kind),
        ) for scope in scopes],
        people=[PlannerPersonOption(
            id=str(user.id), full_name=_user_display_name(user), email=user.email,
            role=_enum_value(user.role), department_name=department_name,
        ) for user, department_name in people],
    )


@planner_schedule_router.post(
    "/integrations/calendar/audit-schedules",
    response_model=PlannerAuditScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_planner_audit_schedule(
    payload: PlannerAuditScheduleCreate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    selected_ids = _dedupe([
        payload.lead_auditor_user_id,
        payload.observer_auditor_user_id,
        payload.assistant_auditor_user_id,
        payload.auditee_user_id,
        *payload.attendee_user_ids,
    ])
    selected_users = _validate_people(db, amo_id=ctx.amo_id, user_ids=selected_ids)
    resolved_scope = _resolve_audit_scope(
        db,
        amo_id=ctx.amo_id,
        audit_scope_id=payload.audit_scope_id,
        audit_scope_code=payload.audit_scope_code,
        kind=payload.kind,
    )
    end_date = payload.next_due_date + timedelta(days=payload.duration_days - 1)
    _validate_one_calendar_year(start=payload.next_due_date, end=end_date)
    candidate = _Candidate(
        subject_type="AUDIT_SCHEDULE",
        subject_id="new",
        title=payload.title.strip(),
        start_date=payload.next_due_date,
        end_date=end_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        location=payload.location,
        user_ids=set(selected_ids),
    )
    conflicts = _collect_conflicts(db, amo_id=ctx.amo_id, candidate=candidate)
    _enforce_conflicts(conflicts, allow=payload.allow_conflicts)

    external_auditees = [item.model_dump(mode="json") for item in payload.external_auditees]
    first_external = external_auditees[0] if external_auditees else {}
    auditee_user = selected_users.get(str(payload.auditee_user_id)) if payload.auditee_user_id else None
    schedule = models.QMSAuditSchedule(
        amo_id=ctx.amo_id,
        domain=payload.domain,
        kind=payload.kind,
        audit_scope_id=resolved_scope.id,
        audit_scope_code=resolved_scope.code,
        frequency=payload.frequency,
        title=payload.title.strip(),
        scope=payload.scope,
        criteria=payload.criteria,
        auditee=payload.auditee or _user_display_name(auditee_user) or f"{first_external.get('first_name', '')} {first_external.get('last_name', '')}".strip() or first_external.get("designation"),
        auditee_email=str(payload.auditee_email or "") or (auditee_user.email if auditee_user else None) or first_external.get("email"),
        auditee_user_id=payload.auditee_user_id,
        external_auditees_json=_serialize_external_auditees(external_auditees),
        lead_auditor_user_id=payload.lead_auditor_user_id,
        observer_auditor_user_id=payload.observer_auditor_user_id,
        assistant_auditor_user_id=payload.assistant_auditor_user_id,
        notify_auditors=payload.notify_auditors,
        notify_auditees=payload.notify_auditees,
        reminder_interval_days=payload.reminder_interval_days,
        duration_days=payload.duration_days,
        next_due_date=payload.next_due_date,
        is_active=payload.automation_active,
        created_by_user_id=ctx.user_id,
    )
    db.add(schedule)
    db.flush()
    metadata = QMSPlannerScheduleMetadata(
        amo_id=ctx.amo_id,
        schedule_id=schedule.id,
        occurrence_date=payload.next_due_date,
        end_date=end_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        timezone_name=payload.timezone_name,
        location=payload.location.strip() if payload.location else None,
        notes=payload.notes,
        responsible_user_id=payload.lead_auditor_user_id,
        attendee_user_ids_json=_dump_json_list(payload.attendee_user_ids),
        external_attendees_json=_dump_json_list([item.model_dump(mode="json") for item in payload.external_attendees]),
        notify_attendees=payload.notify_attendees,
        lifecycle_status="ACTIVE" if payload.automation_active else "SUSPENDED",
        version=1,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(metadata)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule.id),
        action="create_from_planner",
        after={
            "next_due_date": schedule.next_due_date.isoformat(),
            "end_date": end_date.isoformat(),
            "start_time": payload.start_time.isoformat(timespec="minutes"),
            "location": metadata.location,
            "version": metadata.version,
            "conflict_override_reason": payload.conflict_override_reason if conflicts else None,
            "conflicts": [item.model_dump(mode="json") for item in conflicts],
        },
        correlation_id=f"qms-planner-create:{schedule.id}",
        metadata=_audit_metadata(request),
        critical=True,
    )
    notifications_queued = _notify_schedule_change(
        db, schedule=schedule, metadata=metadata, state="created",
        reason=payload.conflict_override_reason or "Created in the Quality Operations Planner.",
    )
    db.commit()
    db.refresh(schedule)
    db.refresh(metadata)
    return _schedule_response(schedule, metadata, notifications_queued=notifications_queued, conflicts=conflicts)


@planner_schedule_router.get(
    "/integrations/calendar/audit-schedules/{schedule_id}",
    response_model=PlannerAuditScheduleResponse,
)
def get_planner_audit_schedule(
    schedule_id: uuid.UUID,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    assert_quality_permission(db, ctx, "qms.calendar.view")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    schedule = db.query(models.QMSAuditSchedule).filter(
        models.QMSAuditSchedule.amo_id == ctx.amo_id,
        models.QMSAuditSchedule.id == schedule_id,
        models.QMSAuditSchedule.deleted_at.is_(None),
    ).first()
    metadata = _metadata_for_schedule(db, amo_id=ctx.amo_id, schedule_id=schedule_id)
    if schedule is None or metadata is None:
        raise HTTPException(status_code=404, detail="Audit schedule not found")
    candidate = _Candidate(
        subject_type="AUDIT_SCHEDULE", subject_id=str(schedule.id), title=schedule.title,
        start_date=schedule.next_due_date,
        end_date=schedule.next_due_date + timedelta(days=max(int(schedule.duration_days or 1), 1) - 1),
        start_time=metadata.start_time, end_time=metadata.end_time, location=metadata.location,
        user_ids=_schedule_user_ids(schedule, metadata),
    )
    conflicts = _collect_conflicts(db, amo_id=ctx.amo_id, candidate=candidate, exclude_schedule_id=str(schedule.id))
    return _schedule_response(schedule, metadata, conflicts=conflicts)


@planner_schedule_router.post(
    "/integrations/calendar/conflicts/check",
    response_model=PlannerConflictCheckResponse,
)
def check_planner_conflicts(
    payload: PlannerAuditScheduleCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerConflictCheckResponse:
    assert_quality_permission(db, ctx, "qms.calendar.view")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    user_ids = _dedupe([
        payload.lead_auditor_user_id, payload.observer_auditor_user_id,
        payload.assistant_auditor_user_id, payload.auditee_user_id, *payload.attendee_user_ids,
    ])
    _validate_people(db, amo_id=ctx.amo_id, user_ids=user_ids)
    conflicts = _collect_conflicts(
        db,
        amo_id=ctx.amo_id,
        candidate=_Candidate(
            subject_type="AUDIT_SCHEDULE", subject_id="preview", title=payload.title,
            start_date=payload.next_due_date,
            end_date=payload.next_due_date + timedelta(days=payload.duration_days - 1),
            start_time=payload.start_time, end_time=payload.end_time, location=payload.location,
            user_ids=set(user_ids),
        ),
    )
    return PlannerConflictCheckResponse(has_conflicts=bool(conflicts), conflicts=conflicts)


@planner_schedule_router.patch(
    "/integrations/calendar/audit-schedules/{schedule_id}",
    response_model=PlannerAuditScheduleResponse,
)
def update_planner_audit_schedule(
    schedule_id: uuid.UUID,
    payload: PlannerAuditScheduleUpdate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    schedule = db.query(models.QMSAuditSchedule).filter(
        models.QMSAuditSchedule.amo_id == ctx.amo_id,
        models.QMSAuditSchedule.id == schedule_id,
        models.QMSAuditSchedule.deleted_at.is_(None),
    ).with_for_update().first()
    metadata = _metadata_for_schedule(db, amo_id=ctx.amo_id, schedule_id=schedule_id, lock=True)
    if schedule is None or metadata is None:
        raise HTTPException(status_code=404, detail="Audit schedule not found")
    _assert_version(metadata, payload.expected_version)
    _validate_people(db, amo_id=ctx.amo_id, user_ids=payload.attendee_user_ids)
    end_date = payload.next_due_date + timedelta(days=payload.duration_days - 1)
    _validate_one_calendar_year(start=payload.next_due_date, end=end_date)
    candidate = _Candidate(
        subject_type="AUDIT_SCHEDULE", subject_id=str(schedule.id), title=schedule.title,
        start_date=payload.next_due_date, end_date=end_date,
        start_time=payload.start_time, end_time=payload.end_time, location=payload.location,
        user_ids=_schedule_user_ids(schedule, metadata).union(payload.attendee_user_ids),
    )
    conflicts = _collect_conflicts(db, amo_id=ctx.amo_id, candidate=candidate, exclude_schedule_id=str(schedule.id))
    _enforce_conflicts(conflicts, allow=payload.allow_conflicts)
    before = {
        "next_due_date": schedule.next_due_date.isoformat(),
        "duration_days": schedule.duration_days,
        "start_time": metadata.start_time.isoformat() if metadata.start_time else None,
        "end_time": metadata.end_time.isoformat() if metadata.end_time else None,
        "location": metadata.location,
        "version": metadata.version,
    }
    schedule.next_due_date = payload.next_due_date
    schedule.duration_days = payload.duration_days
    metadata.occurrence_date = payload.next_due_date
    metadata.end_date = end_date
    metadata.start_time = payload.start_time
    metadata.end_time = payload.end_time
    metadata.timezone_name = payload.timezone_name
    metadata.location = payload.location.strip() if payload.location else None
    metadata.attendee_user_ids_json = _dump_json_list(payload.attendee_user_ids)
    metadata.external_attendees_json = _dump_json_list([item.model_dump(mode="json") for item in payload.external_attendees])
    metadata.notify_attendees = payload.notify_attendees
    metadata.version = int(metadata.version or 1) + 1
    metadata.updated_by_user_id = ctx.user_id
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule.id),
        action="reschedule_resize",
        before=before,
        after={
            "next_due_date": payload.next_due_date.isoformat(),
            "end_date": end_date.isoformat(),
            "start_time": payload.start_time.isoformat(),
            "end_time": payload.end_time.isoformat() if payload.end_time else None,
            "location": metadata.location,
            "version": metadata.version,
            "reason": payload.reason.strip(),
            "conflict_override_reason": payload.conflict_override_reason if conflicts else None,
            "conflicts": [item.model_dump(mode="json") for item in conflicts],
        },
        correlation_id=f"qms-planner-update:{schedule.id}:{metadata.version}",
        metadata=_audit_metadata(request),
        critical=True,
    )
    notifications_queued = _notify_schedule_change(
        db, schedule=schedule, metadata=metadata, state="rescheduled", reason=payload.reason.strip()
    )
    db.commit()
    db.refresh(schedule)
    db.refresh(metadata)
    return _schedule_response(schedule, metadata, notifications_queued=notifications_queued, conflicts=conflicts)


def _change_schedule_state(
    *,
    schedule_id: uuid.UUID,
    active: bool,
    payload: PlannerAuditScheduleStateUpdate,
    request: Request,
    ctx: TenantContext,
    db: Session,
) -> PlannerAuditScheduleResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    schedule = db.query(models.QMSAuditSchedule).filter(
        models.QMSAuditSchedule.amo_id == ctx.amo_id,
        models.QMSAuditSchedule.id == schedule_id,
        models.QMSAuditSchedule.deleted_at.is_(None),
    ).with_for_update().first()
    metadata = _metadata_for_schedule(db, amo_id=ctx.amo_id, schedule_id=schedule_id, lock=True)
    if schedule is None or metadata is None:
        raise HTTPException(status_code=404, detail="Audit schedule not found")
    _assert_version(metadata, payload.expected_version)
    if bool(schedule.is_active) == active and metadata.lifecycle_status == ("ACTIVE" if active else "SUSPENDED"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Schedule automation is already {'active' if active else 'suspended'}.")
    before = {"automation_active": bool(schedule.is_active), "lifecycle_status": metadata.lifecycle_status, "version": metadata.version}
    schedule.is_active = active
    state = "resumed" if active else "suspended"
    metadata.lifecycle_status = "ACTIVE" if active else "SUSPENDED"
    metadata.suspension_reason = None if active else payload.reason.strip()
    metadata.suspended_at = None if active else datetime.now(timezone.utc)
    metadata.suspended_by_user_id = None if active else ctx.user_id
    metadata.version = int(metadata.version or 1) + 1
    metadata.updated_by_user_id = ctx.user_id
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule.id),
        action=state,
        before=before,
        after={"automation_active": active, "lifecycle_status": metadata.lifecycle_status, "reason": payload.reason.strip(), "version": metadata.version},
        correlation_id=f"qms-planner-{state}:{schedule.id}:{metadata.version}",
        metadata=_audit_metadata(request),
        critical=True,
    )
    notifications_queued = _notify_schedule_change(db, schedule=schedule, metadata=metadata, state=state, reason=payload.reason.strip())
    db.commit()
    db.refresh(schedule)
    db.refresh(metadata)
    return _schedule_response(schedule, metadata, notifications_queued=notifications_queued)


@planner_schedule_router.post("/integrations/calendar/audit-schedules/{schedule_id}/suspend", response_model=PlannerAuditScheduleResponse)
def suspend_planner_audit_schedule(
    schedule_id: uuid.UUID,
    payload: PlannerAuditScheduleStateUpdate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    return _change_schedule_state(schedule_id=schedule_id, active=False, payload=payload, request=request, ctx=ctx, db=db)


@planner_schedule_router.post("/integrations/calendar/audit-schedules/{schedule_id}/resume", response_model=PlannerAuditScheduleResponse)
def resume_planner_audit_schedule(
    schedule_id: uuid.UUID,
    payload: PlannerAuditScheduleStateUpdate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    return _change_schedule_state(schedule_id=schedule_id, active=True, payload=payload, request=request, ctx=ctx, db=db)


def _source_record(db: Session, *, amo_id: str, source_type: str, source_id: str, lock: bool) -> dict[str, Any] | None:
    if source_type == "MANAGEMENT_REVIEW":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Management review is currently a read-only Quality surface without an authoritative writable domain record. The planner will not invent a duplicate lifecycle.",
                "required_action": "Add a governed management-review aggregate in the Quality module, then register it as a planner source.",
            },
        )
    spec = _SOURCE_SPECS.get(source_type)
    if spec is None:
        raise HTTPException(status_code=422, detail="Unsupported authoritative planner source.")
    suffix = " FOR UPDATE" if lock and db.get_bind().dialect.name == "postgresql" else ""
    end_projection = f", {spec['end_column']} AS end_date" if spec["end_column"] else ", NULL AS end_date"
    responsible_projection = f", {spec['responsible_column']} AS responsible_user_id" if spec["responsible_column"] else ", NULL AS responsible_user_id"
    location_projection = f", {spec['location_column']} AS location" if spec["location_column"] else ", NULL AS location"
    row = db.execute(text(f"""
        SELECT CAST(id AS TEXT) AS id, {spec['start_column']} AS start_date
               {end_projection}{responsible_projection}{location_projection}
        FROM {spec['table']}
        WHERE amo_id = :amo_id
          AND CAST(id AS TEXT) = :source_id
          AND ({spec['active_predicate']})
        {suffix}
    """), {"amo_id": amo_id, "source_id": source_id}).mappings().first()
    return dict(row) if row else None


def _update_source_record(db: Session, *, amo_id: str, payload: PlannerSourceMetadataUpsert) -> None:
    spec = _SOURCE_SPECS[payload.source_type]
    assignments = [f"{spec['start_column']} = :start_date"]
    params: dict[str, Any] = {"amo_id": amo_id, "source_id": payload.source_id, "start_date": payload.start_date}
    if spec["end_column"]:
        assignments.append(f"{spec['end_column']} = :end_date")
        params["end_date"] = payload.end_date
    if spec["responsible_column"]:
        assignments.append(f"{spec['responsible_column']} = :responsible_user_id")
        params["responsible_user_id"] = payload.responsible_user_id
    if spec["location_column"]:
        assignments.append(f"{spec['location_column']} = :location")
        params["location"] = payload.location
    result = db.execute(text(f"""
        UPDATE {spec['table']}
        SET {', '.join(assignments)}
        WHERE amo_id = :amo_id
          AND CAST(id AS TEXT) = :source_id
          AND ({spec['active_predicate']})
    """), params)
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="The authoritative source left the active planner lifecycle before the update committed.")


@planner_schedule_router.put("/integrations/calendar/source-metadata", response_model=PlannerSourceMetadataResponse)
def upsert_planner_source_metadata(
    payload: PlannerSourceMetadataUpsert,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerSourceMetadataResponse:
    assert_quality_permission(db, ctx, "qms.calendar.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    source = _source_record(db, amo_id=ctx.amo_id, source_type=payload.source_type, source_id=payload.source_id, lock=True)
    if source is None:
        raise HTTPException(status_code=404, detail="Active authoritative source record not found.")
    people = _dedupe([payload.responsible_user_id, *payload.attendee_user_ids])
    _validate_people(db, amo_id=ctx.amo_id, user_ids=people)
    end_date = payload.end_date or payload.start_date
    candidate = _Candidate(
        subject_type=payload.source_type,
        subject_id=payload.source_id,
        title=f"{payload.source_type.replace('_', ' ').title()} commitment",
        start_date=payload.start_date,
        end_date=end_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        location=payload.location,
        user_ids=set(people),
    )
    conflicts = _collect_conflicts(
        db,
        amo_id=ctx.amo_id,
        candidate=candidate,
        exclude_source=(payload.source_type, payload.source_id),
    )
    _enforce_conflicts(conflicts, allow=payload.allow_conflicts)
    metadata = _metadata_for_source(
        db, amo_id=ctx.amo_id, source_type=payload.source_type, source_id=payload.source_id, lock=True
    )
    if metadata is None:
        if payload.expected_version is not None:
            raise HTTPException(status_code=409, detail="Planner metadata did not yet exist; refresh before retrying this versioned update.")
        metadata = QMSPlannerScheduleMetadata(
            amo_id=ctx.amo_id,
            source_type=payload.source_type,
            source_id=payload.source_id,
            version=1,
            created_by_user_id=ctx.user_id,
        )
        db.add(metadata)
    else:
        if payload.expected_version is None:
            raise HTTPException(status_code=428, detail="expected_version is required when updating existing planner metadata.")
        _assert_version(metadata, payload.expected_version)
        metadata.version = int(metadata.version or 1) + 1
    before = {
        "start_date": source.get("start_date").isoformat() if source.get("start_date") else None,
        "end_date": source.get("end_date").isoformat() if source.get("end_date") else None,
        "responsible_user_id": source.get("responsible_user_id"),
        "location": source.get("location"),
    }
    _update_source_record(db, amo_id=ctx.amo_id, payload=payload)
    metadata.occurrence_date = payload.start_date
    metadata.end_date = end_date
    metadata.start_time = payload.start_time
    metadata.end_time = payload.end_time
    metadata.timezone_name = payload.timezone_name
    metadata.location = payload.location.strip() if payload.location else None
    metadata.notes = payload.notes
    metadata.responsible_user_id = payload.responsible_user_id
    metadata.attendee_user_ids_json = _dump_json_list(payload.attendee_user_ids)
    metadata.external_attendees_json = _dump_json_list([item.model_dump(mode="json") for item in payload.external_attendees])
    metadata.notify_attendees = payload.notify_attendees
    metadata.lifecycle_status = "ACTIVE"
    metadata.updated_by_user_id = ctx.user_id
    db.flush()
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type=f"planner_{payload.source_type.lower()}",
        entity_id=payload.source_id,
        action="planner_schedule_update",
        before=before,
        after={
            "start_date": payload.start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "responsible_user_id": payload.responsible_user_id,
            "location": metadata.location,
            "version": metadata.version,
            "reason": payload.reason.strip(),
            "conflict_override_reason": payload.conflict_override_reason if conflicts else None,
            "conflicts": [item.model_dump(mode="json") for item in conflicts],
        },
        correlation_id=f"qms-planner-source:{payload.source_type}:{payload.source_id}:{metadata.version}",
        metadata=_audit_metadata(request),
        critical=True,
    )
    db.commit()
    db.refresh(metadata)
    return PlannerSourceMetadataResponse(
        source_type=payload.source_type,
        source_id=payload.source_id,
        start_date=metadata.occurrence_date,
        end_date=metadata.end_date,
        start_time=metadata.start_time,
        end_time=metadata.end_time,
        timezone_name=metadata.timezone_name,
        location=metadata.location,
        responsible_user_id=metadata.responsible_user_id,
        attendee_user_ids=[str(item) for item in _json_list(metadata.attendee_user_ids_json)],
        external_attendees=[dict(item) for item in _json_list(metadata.external_attendees_json) if isinstance(item, dict)],
        notify_attendees=metadata.notify_attendees,
        lifecycle_status=metadata.lifecycle_status,
        version=metadata.version,
        conflicts=conflicts,
    )


@planner_schedule_router.get("/integrations/calendar/automation-status", response_model=PlannerAutomationStatusResponse)
def planner_automation_status(
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAutomationStatusResponse:
    assert_quality_permission(db, ctx, "qms.calendar.view")
    with _state_lock:
        running = bool(_thread and _thread.is_alive())
    with _last_cycle_lock:
        last_cycle = dict(_last_cycle)
    return PlannerAutomationStatusResponse(
        enabled=_automation_enabled(),
        running=running,
        interval_seconds=_interval_seconds(),
        materialize_lead_days=_materialize_lead_days(),
        timezone_name=_PLANNER_TIMEZONE_NAME,
        last_cycle=last_cycle,
    )
