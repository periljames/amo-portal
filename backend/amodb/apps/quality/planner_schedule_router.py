from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import services as audit_services
from amodb.apps.notifications import service as notification_service
from amodb.database import WriteSessionLocal, close_session_safely, get_write_db

from . import models
from .enums import QMSAuditKind, QMSAuditScheduleFrequency, QMSDomain
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
    "upcoming_notices": 0,
    "day_of_notices": 0,
    "errors": 0,
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
    scopes: list[PlannerScopeOption]
    people: list[PlannerPersonOption]


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

    @model_validator(mode="after")
    def validate_timing(self) -> "PlannerAuditScheduleCreate":
        if self.timezone_name != _PLANNER_TIMEZONE_NAME:
            raise ValueError("Quality planner schedules currently use the tenant timezone Africa/Nairobi.")
        if self.end_time is not None and self.end_time <= self.start_time:
            raise ValueError("End time must be later than start time.")
        self.attendee_user_ids = list(dict.fromkeys(item for item in self.attendee_user_ids if item))
        return self


class PlannerAuditScheduleStateUpdate(BaseModel):
    reason: str = Field(min_length=8, max_length=1000)


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
    created_at: datetime
    notifications_queued: int = 0


class PlannerAutomationStatusResponse(BaseModel):
    enabled: bool
    running: bool
    interval_seconds: int
    materialize_lead_days: int
    timezone_name: str
    last_cycle: dict[str, Any]


def _automation_enabled() -> bool:
    value = (os.getenv("QUALITY_PLANNER_SCHEDULER_ENABLED") or "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


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


def _ensure_metadata_schema(db: Session) -> None:
    """Temporary deployment guard; Alembic remains the authoritative schema path."""
    QMSPlannerScheduleMetadata.__table__.create(bind=db.get_bind(), checkfirst=True)


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


def _user_display_name(user: account_models.User | None) -> str:
    if user is None:
        return ""
    return (
        str(getattr(user, "full_name", "") or "").strip()
        or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        or str(getattr(user, "email", "") or "").strip()
        or str(getattr(user, "id", ""))
    )


def _selected_user_ids(payload: PlannerAuditScheduleCreate) -> list[str]:
    values = [
        payload.lead_auditor_user_id,
        payload.observer_auditor_user_id,
        payload.assistant_auditor_user_id,
        payload.auditee_user_id,
        *payload.attendee_user_ids,
    ]
    return list(dict.fromkeys(str(value) for value in values if value))


def _validate_people(db: Session, *, amo_id: str, user_ids: list[str]) -> dict[str, account_models.User]:
    if not user_ids:
        return {}
    users = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.id.in_(user_ids),
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .all()
    )
    by_id = {str(user.id): user for user in users}
    missing = [user_id for user_id in user_ids if user_id not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "One or more selected participants are inactive, belong to another tenant, or no longer exist.",
                "invalid_user_ids": missing,
            },
        )
    return by_id


def _metadata_for_schedule(db: Session, *, amo_id: str, schedule_id: uuid.UUID) -> QMSPlannerScheduleMetadata | None:
    return (
        db.query(QMSPlannerScheduleMetadata)
        .filter(
            QMSPlannerScheduleMetadata.amo_id == amo_id,
            QMSPlannerScheduleMetadata.schedule_id == schedule_id,
        )
        .first()
    )


def _metadata_for_audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> QMSPlannerScheduleMetadata | None:
    return (
        db.query(QMSPlannerScheduleMetadata)
        .filter(
            QMSPlannerScheduleMetadata.amo_id == amo_id,
            QMSPlannerScheduleMetadata.audit_id == audit_id,
        )
        .first()
    )


def _schedule_response(
    schedule: models.QMSAuditSchedule,
    metadata: QMSPlannerScheduleMetadata | None,
    *,
    notifications_queued: int = 0,
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
        start_time=metadata.start_time if metadata else None,
        end_time=metadata.end_time if metadata else None,
        duration_days=schedule.duration_days,
        timezone_name=metadata.timezone_name if metadata else _PLANNER_TIMEZONE_NAME,
        location=metadata.location if metadata else None,
        scope=schedule.scope,
        criteria=schedule.criteria,
        notes=metadata.notes if metadata else None,
        auditee=schedule.auditee,
        auditee_email=schedule.auditee_email,
        auditee_user_id=schedule.auditee_user_id,
        external_auditees=_deserialize_external_auditees(schedule.external_auditees_json),
        lead_auditor_user_id=schedule.lead_auditor_user_id,
        observer_auditor_user_id=schedule.observer_auditor_user_id,
        assistant_auditor_user_id=schedule.assistant_auditor_user_id,
        attendee_user_ids=[str(item) for item in _json_list(metadata.attendee_user_ids_json if metadata else None)],
        external_attendees=[dict(item) for item in _json_list(metadata.external_attendees_json if metadata else None) if isinstance(item, dict)],
        notify_auditors=bool(schedule.notify_auditors),
        notify_auditees=bool(schedule.notify_auditees),
        notify_attendees=True,
        reminder_interval_days=schedule.reminder_interval_days,
        automation_active=bool(schedule.is_active),
        created_at=schedule.created_at,
        notifications_queued=notifications_queued,
    )


def _recipient_targets(
    db: Session,
    *,
    amo_id: str,
    lead_auditor_user_id: str | None,
    observer_auditor_user_id: str | None,
    assistant_auditor_user_id: str | None,
    auditee_user_id: str | None,
    auditee_email: str | None,
    auditee_label: str | None,
    external_auditees: list[dict[str, Any]],
    attendee_user_ids: list[str],
    external_attendees: list[dict[str, Any]],
    notify_auditors: bool,
    notify_auditees: bool,
    notify_attendees: bool,
) -> list[dict[str, str | None]]:
    roles: list[tuple[str, str | None]] = []
    if notify_auditors:
        roles.extend(
            [
                ("lead_auditor", lead_auditor_user_id),
                ("observer_auditor", observer_auditor_user_id),
                ("assistant_auditor", assistant_auditor_user_id),
            ]
        )
    if notify_auditees:
        roles.append(("auditee", auditee_user_id))
    if notify_attendees:
        roles.extend(("attendee", item) for item in attendee_user_ids)

    user_ids = list(dict.fromkeys(user_id for _, user_id in roles if user_id))
    users = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.id.in_(user_ids),
            account_models.User.is_active.is_(True),
        )
        .all()
        if user_ids
        else []
    )
    users_by_id = {str(user.id): user for user in users}
    recipients: list[dict[str, str | None]] = []
    seen: set[tuple[str | None, str | None]] = set()

    def add(role: str, *, user_id: str | None = None, email: str | None = None, label: str | None = None) -> None:
        user = users_by_id.get(str(user_id)) if user_id else None
        resolved_user_id = str(user.id) if user else None
        resolved_email = str(getattr(user, "email", "") or email or "").strip() or None
        resolved_label = _user_display_name(user) or str(label or resolved_email or role)
        key = (resolved_user_id, resolved_email.lower() if resolved_email else None)
        if key in seen:
            return
        seen.add(key)
        recipients.append(
            {
                "role": role,
                "user_id": resolved_user_id,
                "email": resolved_email,
                "label": resolved_label,
            }
        )

    for role, user_id in roles:
        add(role, user_id=user_id)

    if notify_auditees and auditee_email:
        add("auditee_external", email=auditee_email, label=auditee_label or auditee_email)
    if notify_auditees:
        for item in external_auditees:
            label = (
                f"{item.get('first_name', '')} {item.get('last_name', '')}".strip()
                or str(item.get("designation") or item.get("email") or "External auditee")
            )
            add("auditee_external", email=str(item.get("email") or ""), label=label)
    if notify_attendees:
        for item in external_attendees:
            add(
                "attendee_external",
                email=str(item.get("email") or ""),
                label=str(item.get("name") or item.get("designation") or item.get("email") or "External attendee"),
            )
    return recipients


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
    severity = (
        models.QMSNotificationSeverity.ACTION_REQUIRED
        if action_required
        else models.QMSNotificationSeverity.INFO
    )
    for recipient in recipients:
        user_id = recipient.get("user_id")
        email = recipient.get("email")
        role = recipient.get("role") or "recipient"
        label = recipient.get("label") or email or "recipient"
        if user_id:
            _notify_user(db, user_id, message, severity)
            queued += 1
        if email:
            notification_service.send_email(
                template_key=template_key,
                recipient=email,
                subject=subject,
                context={
                    **context,
                    "recipient_role": role,
                    "recipient_label": label,
                },
                correlation_id=f"{correlation_seed}:{role}:{user_id or email.lower()}",
                critical=True,
                email_class="CRITICAL",
                amo_id=amo_id,
                db=db,
                recipient_user_id=user_id,
                audit_context={
                    "purpose": "qms-planner-notice",
                    "template_key": template_key,
                    "recipient_role": role,
                    "correlation_seed": correlation_seed,
                },
            )
            queued += 1
    return queued


def _schedule_recipients(
    db: Session,
    *,
    schedule: models.QMSAuditSchedule,
    metadata: QMSPlannerScheduleMetadata | None,
) -> list[dict[str, str | None]]:
    return _recipient_targets(
        db,
        amo_id=str(schedule.amo_id),
        lead_auditor_user_id=schedule.lead_auditor_user_id,
        observer_auditor_user_id=schedule.observer_auditor_user_id,
        assistant_auditor_user_id=schedule.assistant_auditor_user_id,
        auditee_user_id=schedule.auditee_user_id,
        auditee_email=schedule.auditee_email,
        auditee_label=schedule.auditee,
        external_auditees=_deserialize_external_auditees(schedule.external_auditees_json),
        attendee_user_ids=[str(item) for item in _json_list(metadata.attendee_user_ids_json if metadata else None)],
        external_attendees=[dict(item) for item in _json_list(metadata.external_attendees_json if metadata else None) if isinstance(item, dict)],
        notify_auditors=bool(schedule.notify_auditors),
        notify_auditees=bool(schedule.notify_auditees),
        notify_attendees=True,
    )


def _audit_recipients(
    db: Session,
    *,
    audit: models.QMSAudit,
    metadata: QMSPlannerScheduleMetadata | None,
) -> list[dict[str, str | None]]:
    return _recipient_targets(
        db,
        amo_id=str(audit.amo_id),
        lead_auditor_user_id=audit.lead_auditor_user_id,
        observer_auditor_user_id=audit.observer_auditor_user_id,
        assistant_auditor_user_id=audit.assistant_auditor_user_id,
        auditee_user_id=audit.auditee_user_id,
        auditee_email=audit.auditee_email,
        auditee_label=audit.auditee,
        external_auditees=_deserialize_external_auditees(audit.external_auditees_json),
        attendee_user_ids=[str(item) for item in _json_list(metadata.attendee_user_ids_json if metadata else None)],
        external_attendees=[dict(item) for item in _json_list(metadata.external_attendees_json if metadata else None) if isinstance(item, dict)],
        notify_auditors=bool(audit.notify_auditors),
        notify_auditees=bool(audit.notify_auditees),
        notify_attendees=True,
    )


def _notify_schedule_created(
    db: Session,
    *,
    schedule: models.QMSAuditSchedule,
    metadata: QMSPlannerScheduleMetadata,
) -> int:
    time_label = metadata.start_time.strftime("%H:%M") if metadata.start_time else "All day"
    return _send_notifications(
        db,
        amo_id=str(schedule.amo_id),
        recipients=_schedule_recipients(db, schedule=schedule, metadata=metadata),
        template_key="qms_planner_schedule_created",
        subject=f"Quality schedule created · {schedule.title}",
        message=(
            f"Quality schedule created: {schedule.title} on {schedule.next_due_date.isoformat()} "
            f"at {time_label} {_PLANNER_TIMEZONE_NAME}."
        ),
        context={
            "schedule_id": str(schedule.id),
            "title": schedule.title,
            "kind": _enum_value(schedule.kind),
            "frequency": _enum_value(schedule.frequency),
            "date": schedule.next_due_date.isoformat(),
            "start_time": time_label,
            "end_time": metadata.end_time.strftime("%H:%M") if metadata.end_time else None,
            "timezone": metadata.timezone_name,
            "location": metadata.location,
            "scope": schedule.scope,
            "criteria": schedule.criteria,
            "automation_active": bool(schedule.is_active),
            "reminder_interval_days": schedule.reminder_interval_days,
        },
        correlation_seed=f"planner-schedule-created:{schedule.id}:{schedule.created_at.isoformat()}",
        action_required=False,
    )


def _notify_schedule_state(
    db: Session,
    *,
    schedule: models.QMSAuditSchedule,
    metadata: QMSPlannerScheduleMetadata | None,
    state: str,
    reason: str,
) -> int:
    active = state == "resumed"
    return _send_notifications(
        db,
        amo_id=str(schedule.amo_id),
        recipients=_schedule_recipients(db, schedule=schedule, metadata=metadata),
        template_key=f"qms_planner_schedule_{state}",
        subject=f"Quality schedule {state} · {schedule.title}",
        message=f"Quality schedule {schedule.title} was {state}. Reason: {reason}",
        context={
            "schedule_id": str(schedule.id),
            "title": schedule.title,
            "state": state,
            "automation_active": active,
            "reason": reason,
            "next_due_date": schedule.next_due_date.isoformat(),
        },
        correlation_seed=f"planner-schedule-{state}:{schedule.id}:{datetime.now(timezone.utc).isoformat()}",
        action_required=not active,
    )


def _accountable_actor_id(db: Session, schedule: models.QMSAuditSchedule) -> str | None:
    if schedule.created_by_user_id:
        creator = (
            db.query(account_models.User)
            .filter(
                account_models.User.id == schedule.created_by_user_id,
                account_models.User.amo_id == schedule.amo_id,
                account_models.User.is_active.is_(True),
            )
            .first()
        )
        if creator:
            return str(creator.id)
    manager = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == schedule.amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.role.in_(
                [
                    account_models.AccountRole.QUALITY_MANAGER,
                    account_models.AccountRole.AMO_ADMIN,
                ]
            ),
        )
        .order_by(account_models.User.role.asc(), account_models.User.id.asc())
        .first()
    )
    return str(manager.id) if manager else None


def _materialize_occurrence(
    db: Session,
    *,
    schedule: models.QMSAuditSchedule,
    actor_user_id: str | None,
) -> models.QMSAudit | None:
    occurrence_date = schedule.next_due_date
    existing_metadata = (
        db.query(QMSPlannerScheduleMetadata)
        .filter(
            QMSPlannerScheduleMetadata.amo_id == schedule.amo_id,
            QMSPlannerScheduleMetadata.source_schedule_id == schedule.id,
            QMSPlannerScheduleMetadata.occurrence_date == occurrence_date,
        )
        .first()
    )
    if existing_metadata and existing_metadata.audit_id:
        existing_audit = (
            db.query(models.QMSAudit)
            .filter(
                models.QMSAudit.amo_id == schedule.amo_id,
                models.QMSAudit.id == existing_metadata.audit_id,
            )
            .first()
        )
        if existing_audit:
            return None

    planned_start = occurrence_date
    planned_end = planned_start + timedelta(days=max(schedule.duration_days, 1) - 1)
    _validate_one_calendar_year(start=planned_start, end=planned_end)
    audit_scope_code = schedule.audit_scope_code or _scope_default_code_for_kind(schedule.kind)
    audit_ref, unit_code, ref_year, ref_sequence = _generate_audit_reference(
        db,
        amo_id=str(schedule.amo_id),
        target_date=planned_start,
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
        planned_start=planned_start,
        planned_end=planned_end,
        created_by_user_id=actor_user_id,
    )
    db.add(audit)
    db.flush()

    template_metadata = _metadata_for_schedule(db, amo_id=str(schedule.amo_id), schedule_id=schedule.id)
    occurrence_metadata = QMSPlannerScheduleMetadata(
        amo_id=str(schedule.amo_id),
        audit_id=audit.id,
        source_schedule_id=schedule.id,
        occurrence_date=occurrence_date,
        start_time=template_metadata.start_time if template_metadata else None,
        end_time=template_metadata.end_time if template_metadata else None,
        timezone_name=template_metadata.timezone_name if template_metadata else _PLANNER_TIMEZONE_NAME,
        location=template_metadata.location if template_metadata else None,
        notes=template_metadata.notes if template_metadata else None,
        attendee_user_ids_json=template_metadata.attendee_user_ids_json if template_metadata else "[]",
        external_attendees_json=template_metadata.external_attendees_json if template_metadata else "[]",
        created_by_user_id=actor_user_id,
    )
    db.add(occurrence_metadata)
    db.flush()

    schedule.last_run_at = datetime.now(timezone.utc)
    if schedule.frequency == QMSAuditScheduleFrequency.ONE_TIME:
        schedule.is_active = False
    else:
        schedule.next_due_date = _advance_schedule_date(schedule, occurrence_date)

    audit_services.log_event(
        db,
        amo_id=str(schedule.amo_id),
        actor_user_id=actor_user_id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="auto_create_from_schedule",
        after={
            "audit_ref": audit.audit_ref,
            "title": audit.title,
            "source_schedule_id": str(schedule.id),
            "occurrence_date": occurrence_date.isoformat(),
            "planned_start": planned_start.isoformat(),
            "planned_end": planned_end.isoformat(),
        },
        correlation_id=f"qms-planner-occurrence:{schedule.id}:{occurrence_date.isoformat()}",
        metadata={"automation": True, "scheduler": "quality-planner"},
        critical=True,
    )
    audit_services.log_event(
        db,
        amo_id=str(schedule.amo_id),
        actor_user_id=actor_user_id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule.id),
        action="auto_run",
        after={
            "audit_id": str(audit.id),
            "audit_ref": audit.audit_ref,
            "occurrence_date": occurrence_date.isoformat(),
            "next_due_date": schedule.next_due_date.isoformat(),
            "is_active": bool(schedule.is_active),
        },
        correlation_id=f"qms-planner-schedule-run:{schedule.id}:{occurrence_date.isoformat()}",
        metadata={"automation": True, "scheduler": "quality-planner"},
    )

    time_label = occurrence_metadata.start_time.strftime("%H:%M") if occurrence_metadata.start_time else "All day"
    _send_notifications(
        db,
        amo_id=str(audit.amo_id),
        recipients=_audit_recipients(db, audit=audit, metadata=occurrence_metadata),
        template_key="qms_planner_audit_materialized",
        subject=f"Audit scheduled · {audit.audit_ref}",
        message=(
            f"Audit {audit.audit_ref} ({audit.title}) is scheduled for {planned_start.isoformat()} "
            f"at {time_label} {occurrence_metadata.timezone_name}."
        ),
        context={
            "audit_id": str(audit.id),
            "audit_ref": audit.audit_ref,
            "title": audit.title,
            "planned_start": planned_start.isoformat(),
            "planned_end": planned_end.isoformat(),
            "start_time": time_label,
            "end_time": occurrence_metadata.end_time.strftime("%H:%M") if occurrence_metadata.end_time else None,
            "timezone": occurrence_metadata.timezone_name,
            "location": occurrence_metadata.location,
            "scope": audit.scope,
            "criteria": audit.criteria,
            "source_schedule_id": str(schedule.id),
        },
        correlation_seed=f"qms-planner-audit-created:{audit.id}",
        action_required=True,
    )
    return audit


def _run_audit_reminders(db: Session, *, today: date) -> tuple[int, int]:
    horizon = today + timedelta(days=90)
    audits = (
        db.query(models.QMSAudit)
        .filter(
            models.QMSAudit.status == models.QMSAuditStatus.PLANNED,
            models.QMSAudit.planned_start.is_not(None),
            models.QMSAudit.planned_start >= today,
            models.QMSAudit.planned_start <= horizon,
            models.QMSAudit.deleted_at.is_(None),
        )
        .order_by(models.QMSAudit.amo_id.asc(), models.QMSAudit.planned_start.asc(), models.QMSAudit.id.asc())
        .all()
    )
    upcoming = 0
    day_of = 0
    now = datetime.now(timezone.utc)
    for audit in audits:
        planned_start = audit.planned_start
        if planned_start is None:
            continue
        metadata = _metadata_for_audit(db, amo_id=str(audit.amo_id), audit_id=audit.id)
        recipients = _audit_recipients(db, audit=audit, metadata=metadata)
        if planned_start == today:
            already_sent_today = bool(
                audit.day_of_notice_sent_at
                and audit.day_of_notice_sent_at.astimezone(_PLANNER_TIMEZONE).date() == today
            )
            if already_sent_today:
                continue
            _send_notifications(
                db,
                amo_id=str(audit.amo_id),
                recipients=recipients,
                template_key="qms_planner_audit_day_of",
                subject=f"Audit today · {audit.audit_ref}",
                message=f"Audit {audit.audit_ref} ({audit.title}) is scheduled for today.",
                context={
                    "audit_id": str(audit.id),
                    "audit_ref": audit.audit_ref,
                    "title": audit.title,
                    "planned_start": planned_start.isoformat(),
                    "start_time": metadata.start_time.strftime("%H:%M") if metadata and metadata.start_time else None,
                    "timezone": metadata.timezone_name if metadata else _PLANNER_TIMEZONE_NAME,
                    "location": metadata.location if metadata else None,
                },
                correlation_seed=f"qms-planner-day-of:{audit.id}:{today.isoformat()}",
                action_required=True,
            )
            audit.day_of_notice_sent_at = now
            day_of += 1
            continue

        days_until = (planned_start - today).days
        reminder_window = max(1, min(int(audit.reminder_interval_days or 7), 60))
        if days_until <= reminder_window and audit.upcoming_notice_sent_at is None:
            _send_notifications(
                db,
                amo_id=str(audit.amo_id),
                recipients=recipients,
                template_key="qms_planner_audit_upcoming",
                subject=f"Upcoming audit · {audit.audit_ref}",
                message=(
                    f"Audit {audit.audit_ref} ({audit.title}) is scheduled for "
                    f"{planned_start.isoformat()} ({days_until} day{'s' if days_until != 1 else ''} remaining)."
                ),
                context={
                    "audit_id": str(audit.id),
                    "audit_ref": audit.audit_ref,
                    "title": audit.title,
                    "planned_start": planned_start.isoformat(),
                    "days_until": days_until,
                    "start_time": metadata.start_time.strftime("%H:%M") if metadata and metadata.start_time else None,
                    "timezone": metadata.timezone_name if metadata else _PLANNER_TIMEZONE_NAME,
                    "location": metadata.location if metadata else None,
                },
                correlation_seed=f"qms-planner-upcoming:{audit.id}:{planned_start.isoformat()}",
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
    acquired = bool(
        db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _AUTOMATION_LOCK_KEY}).scalar()
    )
    try:
        yield acquired
    finally:
        if acquired:
            try:
                db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _AUTOMATION_LOCK_KEY})
            except Exception:
                logger.debug("Quality planner advisory unlock failed", exc_info=True)


def run_quality_planner_cycle() -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "completed_at": None,
        "materialized": 0,
        "upcoming_notices": 0,
        "day_of_notices": 0,
        "errors": 0,
    }
    db = WriteSessionLocal()
    try:
        _ensure_metadata_schema(db)
        with _advisory_lock(db) as acquired:
            if not acquired:
                result["completed_at"] = datetime.now(timezone.utc).isoformat()
                return result
            today = datetime.now(_PLANNER_TIMEZONE).date()
            horizon = today + timedelta(days=_materialize_lead_days())
            schedule_ids = [
                row[0]
                for row in (
                    db.query(models.QMSAuditSchedule.id)
                    .filter(
                        models.QMSAuditSchedule.is_active.is_(True),
                        models.QMSAuditSchedule.next_due_date <= horizon,
                        models.QMSAuditSchedule.deleted_at.is_(None),
                    )
                    .order_by(models.QMSAuditSchedule.next_due_date.asc(), models.QMSAuditSchedule.id.asc())
                    .all()
                )
            ]
            for schedule_id in schedule_ids:
                try:
                    schedule = (
                        db.query(models.QMSAuditSchedule)
                        .filter(
                            models.QMSAuditSchedule.id == schedule_id,
                            models.QMSAuditSchedule.is_active.is_(True),
                            models.QMSAuditSchedule.deleted_at.is_(None),
                        )
                        .with_for_update(skip_locked=True)
                        .first()
                    )
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
                    while (
                        schedule.is_active
                        and schedule.next_due_date <= horizon
                        and occurrence_count < _max_catchup_occurrences()
                    ):
                        audit = _materialize_occurrence(
                            db,
                            schedule=schedule,
                            actor_user_id=actor_user_id,
                        )
                        occurrence_count += 1
                        if audit is not None:
                            result["materialized"] += 1
                        elif schedule.frequency == QMSAuditScheduleFrequency.ONE_TIME:
                            schedule.is_active = False
                        else:
                            schedule.next_due_date = _advance_schedule_date(schedule, schedule.next_due_date)
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    logger.info(
                        "Quality planner occurrence already materialized schedule_id=%s",
                        schedule_id,
                    )
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
        try:
            result = run_quality_planner_cycle()
            logger.info("Quality planner automation cycle completed: %s", result)
        except Exception:
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
        _thread = threading.Thread(
            target=_worker,
            name="quality-planner-scheduler",
            daemon=True,
        )
        _thread.start()


def stop_quality_planner_scheduler() -> None:
    global _thread
    with _state_lock:
        thread = _thread
        _stop_event.set()
        _thread = None
    if thread and thread.is_alive():
        thread.join(timeout=5)


@planner_schedule_router.on_event("startup")
def _start_scheduler() -> None:
    start_quality_planner_scheduler()


@planner_schedule_router.on_event("shutdown")
def _stop_scheduler() -> None:
    stop_quality_planner_scheduler()


@planner_schedule_router.get(
    "/integrations/calendar/schedule-options",
    response_model=PlannerScheduleOptionsResponse,
)
def planner_schedule_options(
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerScheduleOptionsResponse:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    scopes = (
        db.query(models.QMSAuditScope)
        .filter(
            models.QMSAuditScope.amo_id == ctx.amo_id,
            models.QMSAuditScope.is_active.is_(True),
        )
        .order_by(models.QMSAuditScope.sort_order.asc(), models.QMSAuditScope.name.asc())
        .all()
    )
    people = (
        db.query(account_models.User, account_models.Department.name)
        .outerjoin(account_models.Department, account_models.Department.id == account_models.User.department_id)
        .filter(
            account_models.User.amo_id == ctx.amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .order_by(account_models.User.full_name.asc(), account_models.User.email.asc())
        .limit(1000)
        .all()
    )
    return PlannerScheduleOptionsResponse(
        timezone_name=_PLANNER_TIMEZONE_NAME,
        frequencies=[item.value for item in QMSAuditScheduleFrequency],
        kinds=[item.value for item in QMSAuditKind],
        scopes=[
            PlannerScopeOption(
                id=str(scope.id),
                code=scope.code,
                name=scope.name,
                party_level=scope.party_level,
                default_kind=_enum_value(scope.default_kind),
            )
            for scope in scopes
        ],
        people=[
            PlannerPersonOption(
                id=str(user.id),
                full_name=_user_display_name(user),
                email=user.email,
                role=_enum_value(user.role),
                department_name=department_name,
            )
            for user, department_name in people
        ],
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
    _ensure_metadata_schema(db)
    selected_users = _validate_people(db, amo_id=ctx.amo_id, user_ids=_selected_user_ids(payload))

    resolved_scope = _resolve_audit_scope(
        db,
        amo_id=ctx.amo_id,
        audit_scope_id=payload.audit_scope_id,
        audit_scope_code=payload.audit_scope_code,
        kind=payload.kind,
    )
    _validate_one_calendar_year(
        start=payload.next_due_date,
        end=None,
        duration_days=payload.duration_days,
    )
    external_auditees = [item.model_dump(mode="json") for item in payload.external_auditees]
    external_name = None
    external_email = None
    if external_auditees:
        first = external_auditees[0]
        external_name = f"{first.get('first_name', '')} {first.get('last_name', '')}".strip() or first.get("designation")
        external_email = first.get("email")

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
        auditee=payload.auditee or _user_display_name(auditee_user) or external_name,
        auditee_email=str(payload.auditee_email or "") or (auditee_user.email if auditee_user else None) or external_email,
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
        start_time=payload.start_time,
        end_time=payload.end_time,
        timezone_name=payload.timezone_name,
        location=payload.location.strip() if payload.location else None,
        notes=payload.notes,
        attendee_user_ids_json=_dump_json_list(payload.attendee_user_ids),
        external_attendees_json=_dump_json_list([item.model_dump(mode="json") for item in payload.external_attendees]),
        created_by_user_id=ctx.user_id,
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
            "title": schedule.title,
            "kind": _enum_value(schedule.kind),
            "frequency": _enum_value(schedule.frequency),
            "next_due_date": schedule.next_due_date.isoformat(),
            "start_time": payload.start_time.isoformat(timespec="minutes"),
            "end_time": payload.end_time.isoformat(timespec="minutes") if payload.end_time else None,
            "timezone": payload.timezone_name,
            "location": metadata.location,
            "lead_auditor_user_id": schedule.lead_auditor_user_id,
            "observer_auditor_user_id": schedule.observer_auditor_user_id,
            "assistant_auditor_user_id": schedule.assistant_auditor_user_id,
            "auditee_user_id": schedule.auditee_user_id,
            "attendee_user_ids": payload.attendee_user_ids,
            "external_attendee_count": len(payload.external_attendees),
            "automation_active": bool(schedule.is_active),
        },
        correlation_id=f"qms-planner-create:{schedule.id}",
        metadata=_audit_metadata(request),
        critical=True,
    )
    notifications_queued = _notify_schedule_created(db, schedule=schedule, metadata=metadata)
    db.commit()
    db.refresh(schedule)
    db.refresh(metadata)
    return _schedule_response(schedule, metadata, notifications_queued=notifications_queued)


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
    _ensure_metadata_schema(db)
    schedule = (
        db.query(models.QMSAuditSchedule)
        .filter(
            models.QMSAuditSchedule.amo_id == ctx.amo_id,
            models.QMSAuditSchedule.id == schedule_id,
            models.QMSAuditSchedule.deleted_at.is_(None),
        )
        .first()
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Audit schedule not found")
    return _schedule_response(
        schedule,
        _metadata_for_schedule(db, amo_id=ctx.amo_id, schedule_id=schedule.id),
    )


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
    _ensure_metadata_schema(db)
    schedule = (
        db.query(models.QMSAuditSchedule)
        .filter(
            models.QMSAuditSchedule.amo_id == ctx.amo_id,
            models.QMSAuditSchedule.id == schedule_id,
            models.QMSAuditSchedule.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Audit schedule not found")
    if bool(schedule.is_active) == active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Schedule automation is already {'active' if active else 'suspended'}.",
        )
    before = bool(schedule.is_active)
    schedule.is_active = active
    metadata = _metadata_for_schedule(db, amo_id=ctx.amo_id, schedule_id=schedule.id)
    state = "resumed" if active else "suspended"
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule.id),
        action=state,
        before={"automation_active": before},
        after={"automation_active": active, "reason": payload.reason.strip()},
        correlation_id=f"qms-planner-{state}:{schedule.id}:{uuid.uuid4().hex[:12]}",
        metadata=_audit_metadata(request),
        critical=True,
    )
    notifications_queued = _notify_schedule_state(
        db,
        schedule=schedule,
        metadata=metadata,
        state=state,
        reason=payload.reason.strip(),
    )
    db.commit()
    db.refresh(schedule)
    return _schedule_response(schedule, metadata, notifications_queued=notifications_queued)


@planner_schedule_router.post(
    "/integrations/calendar/audit-schedules/{schedule_id}/suspend",
    response_model=PlannerAuditScheduleResponse,
)
def suspend_planner_audit_schedule(
    schedule_id: uuid.UUID,
    payload: PlannerAuditScheduleStateUpdate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    return _change_schedule_state(
        schedule_id=schedule_id,
        active=False,
        payload=payload,
        request=request,
        ctx=ctx,
        db=db,
    )


@planner_schedule_router.post(
    "/integrations/calendar/audit-schedules/{schedule_id}/resume",
    response_model=PlannerAuditScheduleResponse,
)
def resume_planner_audit_schedule(
    schedule_id: uuid.UUID,
    payload: PlannerAuditScheduleStateUpdate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    return _change_schedule_state(
        schedule_id=schedule_id,
        active=True,
        payload=payload,
        request=request,
        ctx=ctx,
        db=db,
    )


@planner_schedule_router.get(
    "/integrations/calendar/automation-status",
    response_model=PlannerAutomationStatusResponse,
)
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
