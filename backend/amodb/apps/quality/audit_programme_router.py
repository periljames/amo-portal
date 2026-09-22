from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from typing import Any, Literal
import random
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from amodb.apps.accounts import models as account_models
from amodb.apps.notifications import service as notification_service
from amodb.database import get_read_db, get_write_db

from . import models
from .audit_programme_models import (
    QualityAuditProgramme,
    QualityAuditProgrammeEvent,
    QualityAuditProgrammeItem,
    QualityAuditUniverseItem,
)
from .audit_programme_occurrence_models import QualityAuditProgrammeOccurrenceLink
from .audit_programme_exports import audit_programme_ics, audit_programme_pdf
from .audit_programme_optimizer import ALGORITHM_VERSION, WEIGHTS, recommended_window, score_surveillance
from .excellence_models import QualityIntelligenceReview
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .schedule_weekend import add_business_days, next_weekday
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/audit-programmes", tags=["Quality audit programme"])

ProgrammeStatus = Literal["DRAFT", "UNDER_REVIEW", "APPROVED", "ACTIVE", "SUPERSEDED", "CLOSED"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
EntityType = Literal[
    "DEPARTMENT", "FACILITY", "STATION", "SUPPLIER", "CONTRACTOR", "PROCESS",
    "CAPABILITY", "APPROVAL_RATING", "AIRCRAFT", "AIRCRAFT_TYPE", "PERSONNEL_GROUP", "OTHER",
]
AuditType = Literal[
    "INTERNAL", "DEPARTMENTAL", "TECHNICAL", "WORK_PACK", "SUPPLIER", "CONTRACTED_FUNCTION",
    "FACILITY", "PERSONNEL", "PRODUCT", "PROCESS", "REGULATORY", "SPECIAL", "REACTIVE", "FOLLOW_UP",
]
Recurrence = Literal["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL", "FIXED_DATES", "CUSTOM", "RISK_TRIGGERED"]
ProgrammeItemState = Literal["PLANNED", "SCHEDULED", "COMPLETED", "DEFERRED", "CANCELLED", "FOLLOW_UP_REQUIRED"]
ProgrammeKind = Literal["INTERNAL", "EXTERNAL", "THIRD_PARTY"]
UniverseProgrammeKind = Literal["INTERNAL", "EXTERNAL", "BOTH"]
_ACTIVE_PROGRAMME_STATUSES = ("DRAFT", "UNDER_REVIEW", "APPROVED", "ACTIVE")
_PROGRAMME_KIND_LABELS: dict[str, str] = {
    "INTERNAL": "Internal Audits",
    "EXTERNAL": "External Audits",
    "THIRD_PARTY": "Third Party Audits",
}

# Platform templates are copied into each tenant's own audit universe. A tenant
# can then rename, tune, or deactivate its copy without changing another tenant.
# The internal set mirrors the controlled QAM/22 annual schedule supplied for
# the portal; external rows cover the common Part-145 contracted-provider cycle.
_STANDARD_AUDIT_AREAS: tuple[dict[str, Any], ...] = (
    {"code": "INT-AIRCRAFT", "kind": "INTERNAL", "type": "AIRCRAFT_TYPE", "label": "Aircraft / product audits", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "INT-LINE-STATIONS", "kind": "INTERNAL", "type": "STATION", "label": "Line stations", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "INT-TECH-RECORDS", "kind": "INTERNAL", "type": "PROCESS", "label": "Technical records & library", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "INT-STORES", "kind": "INTERNAL", "type": "PROCESS", "label": "Stores & procurement", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "INT-TOOLS", "kind": "INTERNAL", "type": "PROCESS", "label": "Tools & equipment", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "INT-WORKSHOPS", "kind": "INTERNAL", "type": "FACILITY", "label": "Workshops", "risk": "MEDIUM", "criticality": "HIGH", "mandatory": True},
    {"code": "INT-HANGAR", "kind": "INTERNAL", "type": "FACILITY", "label": "Hangar", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "INT-PERSONNEL", "kind": "INTERNAL", "type": "PERSONNEL_GROUP", "label": "Technical personnel & training", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "INT-DOCUMENTS", "kind": "INTERNAL", "type": "PROCESS", "label": "Controlled documents & manuals", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "INT-QMS", "kind": "INTERNAL", "type": "PROCESS", "label": "Quality management system", "risk": "HIGH", "criticality": "CRITICAL", "mandatory": True},
    {"code": "INT-SMS", "kind": "INTERNAL", "type": "PROCESS", "label": "Safety management system", "risk": "HIGH", "criticality": "CRITICAL", "mandatory": True},
    {"code": "EXT-REGULATOR", "kind": "EXTERNAL", "type": "OTHER", "label": "Regulatory authority oversight", "risk": "HIGH", "criticality": "CRITICAL", "mandatory": True},
    {"code": "EXT-MAINTENANCE", "kind": "EXTERNAL", "type": "CONTRACTOR", "label": "Contracted maintenance organisations", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "EXT-SUPPLIERS", "kind": "EXTERNAL", "type": "SUPPLIER", "label": "Parts & material suppliers", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "EXT-CALIBRATION", "kind": "EXTERNAL", "type": "CONTRACTOR", "label": "Calibration service providers", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
    {"code": "EXT-TRAINING", "kind": "EXTERNAL", "type": "CONTRACTOR", "label": "External training providers", "risk": "MEDIUM", "criticality": "HIGH", "mandatory": True},
    {"code": "EXT-LINE-STATIONS", "kind": "EXTERNAL", "type": "STATION", "label": "Contracted line stations", "risk": "HIGH", "criticality": "HIGH", "mandatory": True},
)


def _programme_kind_title(kind: ProgrammeKind, year: int) -> str:
    return f"{_PROGRAMME_KIND_LABELS[kind]} ({year})"


def _assert_programme_kind_available(db: Session, *, amo_id: str, year: int, kind: ProgrammeKind) -> None:
    conflict = (
        db.query(QualityAuditProgramme.id)
        .filter(
            QualityAuditProgramme.amo_id == amo_id,
            QualityAuditProgramme.programme_year == year,
            QualityAuditProgramme.programme_kind == kind,
            QualityAuditProgramme.status.in_(_ACTIVE_PROGRAMME_STATUSES),
        )
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An active {_PROGRAMME_KIND_LABELS[kind]} programme already exists for {year}. Amend or close it before creating another.",
        )


def _normalise_fixed_dates(values: list[str] | None) -> list[str]:
    normalized: set[str] = set()
    for value in values or []:
        raw = str(value or "").strip()
        try:
            parsed = date.fromisoformat(f"2000-{raw}")
        except ValueError as exc:
            raise ValueError(f"Invalid recurring date '{raw}'. Use MM-DD, for example 04-15.") from exc
        normalized.add(parsed.strftime("%m-%d"))
    return sorted(normalized)


def _validate_default_timing(start_time: time, end_time: time, duration_days: int) -> None:
    if not (time(9) <= start_time <= time(17)) or not (time(9) <= end_time <= time(17)):
        raise ValueError("Audit times must be between 09:00 and 17:00 tenant local time.")
    if end_time <= start_time:
        raise ValueError("Audit end time must be after start time; overnight audits are not permitted.")
    if not 1 <= duration_days <= 90:
        raise ValueError("Audit duration must be between 1 and 90 working days.")


class ProgrammeCreate(BaseModel):
    programme_year: int = Field(ge=2000, le=2200)
    programme_kind: ProgrammeKind = "INTERNAL"
    title: str | None = Field(default=None, min_length=3, max_length=255)
    objectives: list[str] = Field(default_factory=list)
    regulatory_basis: list[str | dict[str, Any]] = Field(default_factory=list)
    period_start: date
    period_end: date
    owner_user_id: str | None = Field(default=None, max_length=36)
    copy_previous_year: bool = False
    rotate_auditors: bool = False
    apply_hybrid_seed: bool = False

    @model_validator(mode="after")
    def valid_period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if self.period_start.year != self.programme_year or self.period_end.year != self.programme_year:
            raise ValueError("The programme period must stay within the selected calendar year.")
        if self.rotate_auditors and not self.copy_previous_year:
            raise ValueError("Auditor rotation requires carrying forward last year's audits.")
        return self


class ProgrammePatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    objectives: list[str] | None = None
    regulatory_basis: list[str | dict[str, Any]] | None = None
    period_start: date | None = None
    period_end: date | None = None
    owner_user_id: str | None = Field(default=None, max_length=36)
    reason: str = Field(min_length=3)


class ProgrammeTransition(BaseModel):
    target_status: ProgrammeStatus
    reason: str = Field(min_length=3)


class ProgrammeAmendment(BaseModel):
    reason: str = Field(min_length=3)
    title: str | None = Field(default=None, min_length=3, max_length=255)


class UniverseCreate(BaseModel):
    entity_type: EntityType
    programme_kind: UniverseProgrammeKind = "BOTH"
    display_label: str = Field(min_length=2, max_length=255)
    source_owner_module: str = Field(min_length=2, max_length=80)
    source_type: str = Field(min_length=2, max_length=64)
    source_id: str = Field(min_length=1, max_length=160)
    source_route: str | None = Field(default=None, max_length=500)
    risk_classification: RiskLevel = "MEDIUM"
    regulatory_criticality: RiskLevel = "MEDIUM"
    surveillance_interval_days: int | None = Field(default=None, ge=1, le=3650)
    mandatory_surveillance: bool = False
    notes: str | None = None


class UniversePatch(BaseModel):
    programme_kind: UniverseProgrammeKind | None = None
    display_label: str | None = Field(default=None, min_length=2, max_length=255)
    source_route: str | None = Field(default=None, max_length=500)
    risk_classification: RiskLevel | None = None
    regulatory_criticality: RiskLevel | None = None
    surveillance_interval_days: int | None = Field(default=None, ge=1, le=3650)
    mandatory_surveillance: bool | None = None
    active: bool | None = None
    notes: str | None = None


def _normalise_supporting_auditors(
    user_ids: list[str] | None,
    *,
    lead_auditor_user_id: str | None = None,
    observer_auditor_user_id: str | None = None,
) -> list[str]:
    normalized: list[str] = []
    for value in user_ids or []:
        user_id = str(value or "").strip()
        if (
            not user_id
            or user_id in {lead_auditor_user_id, observer_auditor_user_id}
            or user_id in normalized
        ):
            continue
        if len(user_id) > 36:
            raise ValueError("Auditor user identifiers cannot exceed 36 characters.")
        normalized.append(user_id)
    return normalized


def _working_day_count(start: date, end: date) -> int:
    """Return the inclusive weekday duration represented by a planned date range."""
    if end < start:
        raise ValueError("target_end must be on or after target_start")
    cursor = start
    count = 0
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return max(count, 1)


class ProgrammeItemCreate(BaseModel):
    universe_item_id: str = Field(max_length=36)
    audit_type: AuditType | None = None
    title: str = Field(min_length=3, max_length=255)
    purpose: str | None = None
    scope: str = Field(min_length=3)
    criteria: list[str | dict[str, Any]] = Field(default_factory=list)
    mandatory_surveillance: bool = False
    recurrence: Recurrence = "ONE_TIME"
    custom_interval_days: int | None = Field(default=None, ge=1, le=3650)
    fixed_dates: list[str] = Field(default_factory=list, max_length=24)
    non_working_day_policy: Literal["NEXT_WORKING_DAY"] = "NEXT_WORKING_DAY"
    default_start_time: time = time(hour=9)
    default_end_time: time = time(hour=17)
    default_duration_days: int = Field(default=1, ge=1, le=90)
    default_location: str | None = Field(default=None, max_length=255)
    lead_auditor_user_id: str | None = Field(default=None, max_length=36)
    observer_auditor_user_id: str | None = Field(default=None, max_length=36)
    supporting_auditor_user_ids: list[str] = Field(default_factory=list, max_length=50)
    auditee_user_id: str | None = Field(default=None, max_length=36)
    notify_auditors: bool = True
    notify_auditees: bool = True
    auto_schedule: bool = False
    target_start: date | None = None
    target_end: date | None = None
    prioritization_basis: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_schedule(self):
        if (
            self.lead_auditor_user_id
            and self.observer_auditor_user_id == self.lead_auditor_user_id
        ):
            raise ValueError("The lead auditor cannot also be the observer.")
        if self.target_start and self.target_end and self.target_end < self.target_start:
            raise ValueError("target_end must be on or after target_start")
        if self.recurrence == "CUSTOM" and not self.custom_interval_days:
            raise ValueError("CUSTOM recurrence requires custom_interval_days")
        self.fixed_dates = _normalise_fixed_dates(self.fixed_dates)
        if self.recurrence == "FIXED_DATES" and not self.fixed_dates:
            raise ValueError("Specific-date recurrence requires at least one calendar date.")
        if self.auto_schedule and self.recurrence != "FIXED_DATES":
            raise ValueError("Automatic schedule generation is available for specific-date recurrence.")
        self.supporting_auditor_user_ids = _normalise_supporting_auditors(
            self.supporting_auditor_user_ids,
            lead_auditor_user_id=self.lead_auditor_user_id,
            observer_auditor_user_id=self.observer_auditor_user_id,
        )
        if self.recurrence != "FIXED_DATES" and self.target_start and self.target_end:
            self.default_duration_days = _working_day_count(self.target_start, self.target_end)
        _validate_default_timing(self.default_start_time, self.default_end_time, self.default_duration_days)
        return self


class ProgrammeItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    purpose: str | None = None
    scope: str | None = Field(default=None, min_length=3)
    criteria: list[str | dict[str, Any]] | None = None
    mandatory_surveillance: bool | None = None
    recurrence: Recurrence | None = None
    custom_interval_days: int | None = Field(default=None, ge=1, le=3650)
    fixed_dates: list[str] | None = Field(default=None, max_length=24)
    non_working_day_policy: Literal["NEXT_WORKING_DAY"] | None = None
    default_start_time: time | None = None
    default_end_time: time | None = None
    default_duration_days: int | None = Field(default=None, ge=1, le=90)
    default_location: str | None = Field(default=None, max_length=255)
    lead_auditor_user_id: str | None = Field(default=None, max_length=36)
    observer_auditor_user_id: str | None = Field(default=None, max_length=36)
    supporting_auditor_user_ids: list[str] | None = Field(default=None, max_length=50)
    auditee_user_id: str | None = Field(default=None, max_length=36)
    notify_auditors: bool | None = None
    notify_auditees: bool | None = None
    auto_schedule: bool | None = None
    target_start: date | None = None
    target_end: date | None = None
    prioritization_basis: list[dict[str, Any]] | None = None
    state: ProgrammeItemState | None = None
    deferral_reason: str | None = None
    cancellation_reason: str | None = None
    reason: str = Field(min_length=3)

    @model_validator(mode="after")
    def validate_fixed_date_input(self):
        if self.fixed_dates is not None:
            self.fixed_dates = _normalise_fixed_dates(self.fixed_dates)
        # Empty FIXED_DATES is allowed when cancelling the requirement (clear last month).
        if self.recurrence == "FIXED_DATES" and self.fixed_dates == [] and self.state != "CANCELLED":
            raise ValueError("Specific-date recurrence requires at least one calendar date, or cancel the requirement.")
        return self


class ProgrammeQualityReview(BaseModel):
    decision: Literal["FORWARD", "RETURN"]
    reason: str = Field(min_length=3)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_standard_audit_areas(db: Session, *, amo_id: str, actor_user_id: str) -> int:
    """Materialise missing platform templates as editable tenant-owned rows."""

    # Serialise first-time catalogue materialisation for concurrent tenant
    # administrators; the existing source uniqueness constraint remains the
    # final duplicate guard.
    db.query(account_models.AMO.id).filter(account_models.AMO.id == amo_id).with_for_update().first()
    existing_codes = {
        str(source_id)
        for (source_id,) in db.query(QualityAuditUniverseItem.source_id).filter(
            QualityAuditUniverseItem.amo_id == amo_id,
            QualityAuditUniverseItem.source_owner_module == "QUALITY_STANDARD",
            QualityAuditUniverseItem.source_type == "AUDIT_AREA_TEMPLATE",
        ).all()
    }
    now = _utcnow()
    created = 0
    for template in _STANDARD_AUDIT_AREAS:
        if template["code"] in existing_codes:
            continue
        db.add(QualityAuditUniverseItem(
            amo_id=amo_id,
            entity_type=template["type"],
            programme_kind=template["kind"],
            display_label=template["label"],
            source_owner_module="QUALITY_STANDARD",
            source_type="AUDIT_AREA_TEMPLATE",
            source_id=template["code"],
            risk_classification=template["risk"],
            regulatory_criticality=template["criticality"],
            surveillance_interval_days=365,
            mandatory_surveillance=bool(template["mandatory"]),
            active=True,
            notes="Platform standard copied into this tenant. Changes apply only to this tenant.",
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
            created_at=now,
            updated_at=now,
        ))
        created += 1
    if created:
        db.flush()
    return created


def _validate_programme_owner(db: Session, *, amo_id: str, user_id: str | None) -> None:
    if user_id is None:
        return
    owner = db.query(account_models.User.id).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Programme owner must be an active human user in this tenant.",
        )


def _validate_item_people(db: Session, *, amo_id: str, user_ids: list[str | None]) -> None:
    selected = {str(user_id) for user_id in user_ids if user_id}
    if not selected:
        return
    existing = {
        str(row[0])
        for row in db.query(account_models.User.id).filter(
            account_models.User.amo_id == amo_id,
            account_models.User.id.in_(selected),
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        ).all()
    }
    if existing != selected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Every selected auditor and auditee must be an active human user in this tenant.",
        )


def _validate_item_auditor_privileges(
    db: Session,
    *,
    amo_id: str,
    lead_user_id: str | None,
    observer_user_id: str | None,
    supporting_user_ids: list[str],
) -> None:
    # Imported lazily because the planner composes this programme router during
    # Quality application startup. The shared check is nevertheless the sole
    # runtime source of auditor eligibility for both programme and calendar.
    from .planner_schedule_router import _validate_auditor_assignments

    _validate_auditor_assignments(
        db,
        amo_id=amo_id,
        lead_user_id=lead_user_id,
        observer_user_id=observer_user_id,
        assistant_user_id=None,
        supporting_user_ids=supporting_user_ids,
    )


def _validate_item_location(
    db: Session,
    *,
    amo_id: str,
    location_code: str | None,
    required: bool = False,
) -> None:
    code = str(location_code or "").strip()
    if not code:
        if required:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Facility and station audits require a configured tenant location.",
            )
        return
    from amodb.apps.foundations import models as foundation_models

    location = db.query(foundation_models.BaseStation.id).filter(
        foundation_models.BaseStation.amo_id == amo_id,
        foundation_models.BaseStation.code == code,
        foundation_models.BaseStation.is_active.is_(True),
    ).first()
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select an active physical location configured for this tenant.",
        )


def _fixed_date(programme: QualityAuditProgramme, month_day: str) -> date:
    try:
        return date.fromisoformat(f"{programme.programme_year}-{month_day}")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Recurring date {month_day} is not valid in {programme.programme_year}.",
        ) from exc


def _apply_fixed_date_window(programme: QualityAuditProgramme, values: dict[str, Any]) -> None:
    if values.get("recurrence") != "FIXED_DATES":
        return
    fixed_dates = _normalise_fixed_dates(values.get("fixed_dates"))
    if not fixed_dates:
        raise HTTPException(status_code=422, detail="Add at least one specific calendar date.")
    duration_days = int(values.get("default_duration_days") or 1)
    requested = [_fixed_date(programme, value) for value in fixed_dates]
    resolved_starts = [next_weekday(value) for value in requested]
    if len(set(resolved_starts)) != len(resolved_starts):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Two selected dates resolve to the same working day. Remove one of the duplicate audit dates.",
        )
    resolved_ends = [add_business_days(value, duration_days - 1) for value in resolved_starts]
    if min(resolved_starts) < programme.period_start or max(resolved_ends) > programme.period_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Specific audit dates and their working-day duration must stay inside the programme period.",
        )
    values["fixed_dates"] = fixed_dates
    values["target_start"] = min(resolved_starts)
    values["target_end"] = max(resolved_ends)
    values["auto_schedule"] = True


def _programme_ref(year: int, revision: int) -> tuple[str, str]:
    series = f"AP-{year}-{uuid.uuid4().hex[:8].upper()}"
    return f"{series}-R{revision:02d}", series


def _universe_dict(item: QualityAuditUniverseItem, aircraft: Any | None = None) -> dict[str, Any]:
    payload = {
        "id": str(item.id), "entity_type": item.entity_type, "display_label": item.display_label,
        "programme_kind": item.programme_kind,
        "source_owner_module": item.source_owner_module, "source_type": item.source_type,
        "source_id": item.source_id, "source_route": item.source_route,
        "risk_classification": item.risk_classification,
        "regulatory_criticality": item.regulatory_criticality,
        "surveillance_interval_days": item.surveillance_interval_days,
        "mandatory_surveillance": item.mandatory_surveillance, "active": item.active,
        "notes": item.notes, "created_at": item.created_at, "updated_at": item.updated_at,
    }
    if aircraft is not None:
        payload["aircraft"] = {
            "tail_number": aircraft.registration,
            "model": aircraft.model or aircraft.aircraft_model_code,
            "msn": aircraft.serial_number,
        }
    else:
        payload["aircraft"] = None
    payload["origin"] = "PLATFORM_STANDARD" if item.source_owner_module == "QUALITY_STANDARD" else "TENANT"
    return payload


def _aircraft_by_source_id(
    db: Session,
    *,
    amo_id: str,
    items: list[QualityAuditUniverseItem],
) -> dict[str, Any]:
    serial_numbers = {
        str(item.source_id)
        for item in items
        if item.entity_type == "AIRCRAFT"
        and item.source_owner_module == "FLEET"
        and item.source_type == "AIRCRAFT"
    }
    if not serial_numbers:
        return {}
    # Local import avoids coupling the Quality router's module bootstrap to the
    # Fleet router while still treating Fleet as the authoritative source.
    from amodb.apps.fleet.models import Aircraft

    rows = db.query(Aircraft).filter(
        Aircraft.amo_id == amo_id,
        Aircraft.serial_number.in_(serial_numbers),
    ).all()
    return {str(row.serial_number): row for row in rows}


def _item_dict(item: QualityAuditProgrammeItem) -> dict[str, Any]:
    return {
        "id": str(item.id), "programme_id": str(item.programme_id),
        "universe_item_id": str(item.universe_item_id), "audit_type": item.audit_type,
        "title": item.title, "purpose": item.purpose, "scope": item.scope, "criteria": item.criteria,
        "mandatory_surveillance": item.mandatory_surveillance, "recurrence": item.recurrence,
        "custom_interval_days": item.custom_interval_days, "target_start": item.target_start,
        "target_end": item.target_end, "state": item.state,
        "fixed_dates": list(item.fixed_dates or []),
        "non_working_day_policy": item.non_working_day_policy,
        "default_start_time": item.default_start_time,
        "default_end_time": item.default_end_time,
        "default_duration_days": item.default_duration_days,
        "default_location": item.default_location,
        "lead_auditor_user_id": item.lead_auditor_user_id,
        "observer_auditor_user_id": item.observer_auditor_user_id,
        "supporting_auditor_user_ids": list(item.supporting_auditor_user_ids or []),
        "auditee_user_id": item.auditee_user_id,
        "notify_auditors": item.notify_auditors,
        "notify_auditees": item.notify_auditees,
        "auto_schedule": item.auto_schedule,
        "prioritization_basis": item.prioritization_basis,
        "deferral_reason": item.deferral_reason, "cancellation_reason": item.cancellation_reason,
        "auditable_entity": _universe_dict(item.universe_item) if item.universe_item else None,
        "created_at": item.created_at, "updated_at": item.updated_at,
    }


def _programme_snapshot(programme: QualityAuditProgramme) -> dict[str, Any]:
    return {
        "id": str(programme.id), "programme_ref": programme.programme_ref,
        "programme_series": programme.programme_series, "programme_year": programme.programme_year,
        "programme_kind": programme.programme_kind,
        "revision_no": programme.revision_no, "title": programme.title,
        "assurance_model": "HYBRID",
        "continuous_monitoring_enabled": bool(programme.continuous_monitoring_enabled),
        "optimizer_version": programme.optimizer_version,
        "objectives": programme.objectives, "regulatory_basis": programme.regulatory_basis,
        "status": programme.status, "period_start": programme.period_start.isoformat(),
        "period_end": programme.period_end.isoformat(), "owner_user_id": programme.owner_user_id,
        "supersedes_programme_id": programme.supersedes_programme_id,
        "submitted_by_user_id": programme.submitted_by_user_id,
        "submitted_at": programme.submitted_at.isoformat() if programme.submitted_at else None,
        "quality_reviewed_by_user_id": programme.quality_reviewed_by_user_id,
        "quality_reviewed_at": programme.quality_reviewed_at.isoformat() if programme.quality_reviewed_at else None,
        "approved_by_user_id": programme.approved_by_user_id,
        "approved_at": programme.approved_at.isoformat() if programme.approved_at else None,
    }


def _programme_readiness(programme: QualityAuditProgramme, *, mandatory_coverage_gaps: int = 0) -> dict[str, Any]:
    items = [item for item in list(programme.items or []) if item.state != "CANCELLED"]
    blockers: list[dict[str, str]] = []
    if not items:
        blockers.append({"code": "NO_REQUIREMENTS", "message": "Add at least one active audit requirement before approval."})
    if not list(programme.regulatory_basis or []):
        blockers.append({"code": "NO_COMPLIANCE_BASIS", "message": "Add the applicable regulatory, approval, manual or contractual baseline before approval."})
    if not programme.owner_user_id:
        blockers.append({"code": "NO_OWNER", "message": "Assign an accountable programme owner before approval."})
    if mandatory_coverage_gaps:
        blockers.append({
            "code": "MANDATORY_COVERAGE_GAP",
            "message": f"{mandatory_coverage_gaps} mandatory surveillance requirement(s) due in this programme period are not covered.",
        })
    for item in items:
        if getattr(item, "recurrence", None) == "FIXED_DATES":
            if not list(getattr(item, "fixed_dates", None) or []):
                blockers.append({"code": "MISSING_FIXED_DATES", "message": f"{item.title}: add at least one recurring calendar date."})
            if not getattr(item, "auto_schedule", False):
                blockers.append({"code": "AUTO_SCHEDULE_DISABLED", "message": f"{item.title}: enable automatic schedule generation for its specific dates."})
            if not getattr(item, "lead_auditor_user_id", None):
                blockers.append({"code": "MISSING_LEAD_AUDITOR", "message": f"{item.title}: assign a lead auditor before approval."})
        if not item.target_start or not item.target_end:
            blockers.append({"code": "MISSING_TARGET_WINDOW", "message": f"{item.title}: set a target start and end window."})
        elif item.target_start < programme.period_start or item.target_end > programme.period_end:
            blockers.append({"code": "OUTSIDE_PROGRAMME_PERIOD", "message": f"{item.title}: target window must remain inside the programme period."})
        if not list(item.criteria or []):
            blockers.append({"code": "MISSING_CRITERIA", "message": f"{item.title}: add the audit criteria before approval."})
    mandatory = [item for item in items if item.mandatory_surveillance]
    high_risk = [
        item for item in items
        if item.universe_item and item.universe_item.risk_classification in {"HIGH", "CRITICAL"}
    ]
    awaiting_manual_schedule = [
        item for item in items
        if item.state == "PLANNED"
        and not (
            getattr(item, "recurrence", None) == "FIXED_DATES"
            and getattr(item, "auto_schedule", False)
        )
    ]
    return {
        "ready_for_approval": not blockers,
        "blockers": blockers,
        "requirement_count": len(items),
        "mandatory_requirement_count": len(mandatory),
        "mandatory_unscheduled_count": sum(1 for item in awaiting_manual_schedule if item.mandatory_surveillance),
        "high_risk_requirement_count": len(high_risk),
        "unscheduled_requirement_count": len(awaiting_manual_schedule),
        "mandatory_coverage_gap_count": mandatory_coverage_gaps,
    }


def _programme_dict(programme: QualityAuditProgramme, *, detail: bool = False) -> dict[str, Any]:
    items = list(programme.items or [])
    counts = {state: 0 for state in ["PLANNED", "SCHEDULED", "COMPLETED", "DEFERRED", "CANCELLED", "FOLLOW_UP_REQUIRED"]}
    for item in items:
        counts[item.state] = counts.get(item.state, 0) + 1
    auto_scheduled_on_publication = sum(
        1 for item in items
        if item.state == "PLANNED"
        and getattr(item, "recurrence", None) == "FIXED_DATES"
        and getattr(item, "auto_schedule", False)
    )
    result: dict[str, Any] = {
        **_programme_snapshot(programme),
        "owner_user_id": programme.owner_user_id,
        "submitted_by_user_id": programme.submitted_by_user_id, "submitted_at": programme.submitted_at,
        "quality_reviewed_by_user_id": programme.quality_reviewed_by_user_id,
        "quality_reviewed_at": programme.quality_reviewed_at,
        "approved_by_user_id": programme.approved_by_user_id, "approved_at": programme.approved_at,
        "activated_at": programme.activated_at, "closed_at": programme.closed_at,
        "created_at": programme.created_at, "updated_at": programme.updated_at,
        "metrics": {
            "planned_audit_count": sum(1 for item in items if item.state != "CANCELLED"),
            "completed_audit_count": counts["COMPLETED"],
            "deferred_audit_count": counts["DEFERRED"], "cancelled_audit_count": counts["CANCELLED"],
            "follow_up_audit_count": counts["FOLLOW_UP_REQUIRED"], "scheduled_audit_count": counts["SCHEDULED"],
            "unscheduled_audit_count": counts["PLANNED"] - auto_scheduled_on_publication,
        },
        "readiness": _programme_readiness(programme),
    }
    if detail:
        result["items"] = [_item_dict(item) for item in items]
        result["events"] = [
            {"id": str(event.id), "event_type": event.event_type, "reason": event.reason,
             "before_snapshot": event.before_snapshot, "after_snapshot": event.after_snapshot,
             "actor_user_id": event.actor_user_id, "created_at": event.created_at}
            for event in list(programme.events or [])
        ]
    return result


def _query(db: Session, amo_id: str):
    return db.query(QualityAuditProgramme).filter(QualityAuditProgramme.amo_id == amo_id)


def _load_programme(db: Session, amo_id: str, programme_id: str, *, for_update: bool = False) -> QualityAuditProgramme:
    query = (_query(db, amo_id)
             .options(selectinload(QualityAuditProgramme.items).selectinload(QualityAuditProgrammeItem.universe_item),
                      selectinload(QualityAuditProgramme.events))
             .filter(QualityAuditProgramme.id == programme_id))
    if for_update:
        query = query.with_for_update(of=QualityAuditProgramme)
    programme = query.first()
    if not programme:
        raise HTTPException(status_code=404, detail="Audit programme not found.")
    return programme


def _event(db: Session, programme: QualityAuditProgramme, ctx: TenantContext, event_type: str, reason: str,
           before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
    db.add(QualityAuditProgrammeEvent(
        amo_id=ctx.amo_id, programme_id=programme.id, event_type=event_type, reason=reason.strip(),
        before_snapshot=before, after_snapshot=after, actor_user_id=ctx.user_id, created_at=_utcnow(),
    ))


def _programme_action_url(ctx: TenantContext, programme: QualityAuditProgramme) -> str:
    return (
        f"/maintenance/{ctx.amo_code}/quality/audits/program"
        f"?tab=approval&programme={programme.id}"
    )


def _active_programme_role_users(
    db: Session,
    *,
    amo_id: str,
    role_name: str,
    exclude_user_id: str | None = None,
) -> list[account_models.User]:
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.role == account_models.AccountRole(role_name),
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )
    if exclude_user_id:
        query = query.filter(account_models.User.id != exclude_user_id)
    return query.all()


def _notify_programme_users(
    db: Session,
    *,
    programme: QualityAuditProgramme,
    ctx: TenantContext,
    role_names: tuple[str, ...] = (),
    extra_user_ids: tuple[str | None, ...] = (),
    message: str,
    subject: str,
    template_key: str,
    correlation_suffix: str,
    action_required: bool,
) -> int:
    role_values = [account_models.AccountRole(value) for value in role_names]
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )
    users = query.filter(account_models.User.role.in_(role_values)).all() if role_values else []
    extra_ids = {str(value) for value in extra_user_ids if value}
    if extra_ids:
        users.extend(query.filter(account_models.User.id.in_(extra_ids)).all())
    recipients = {str(user.id): user for user in users}
    recipients.pop(ctx.user_id, None)
    action_url = _programme_action_url(ctx, programme)
    severity = models.QMSNotificationSeverity.ACTION_REQUIRED if action_required else models.QMSNotificationSeverity.INFO
    queued = 0
    for user_id, user in recipients.items():
        db.add(models.QMSNotification(
            amo_id=ctx.amo_id,
            user_id=user_id,
            message=message,
            severity=severity,
            created_by_user_id=ctx.user_id,
            action_url=action_url,
            action_label="Open audit programme",
            entity_type="AUDIT_PROGRAMME",
            entity_id=str(programme.id),
        ))
        queued += 1
        if getattr(user, "email", None):
            try:
                notification_service.send_email(
                    template_key=template_key,
                    recipient=user.email,
                    subject=subject,
                    context={
                        "programme_id": str(programme.id),
                        "programme_ref": programme.programme_ref,
                        "programme_title": programme.title,
                        "message": message,
                        "action_url": action_url,
                    },
                    correlation_id=f"audit-programme:{programme.id}:{correlation_suffix}:{user_id}",
                    critical=False,
                    amo_id=ctx.amo_id,
                    db=db,
                    recipient_user_id=user_id,
                    audit_context={"purpose": "audit-programme-approval", "stage": correlation_suffix},
                )
                queued += 1
            except Exception:
                # Approval is never blocked by an unavailable optional delivery provider;
                # the durable in-app notification above remains authoritative.
                continue
    return queued


def _assert_editable(programme: QualityAuditProgramme) -> None:
    if programme.status != "DRAFT":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Only a draft programme may be edited. A submitted revision is frozen; return it to draft or create an amendment.")


def _validate_item_window(programme: QualityAuditProgramme, start: date | None, end: date | None) -> None:
    if start and start < programme.period_start:
        raise HTTPException(status_code=422, detail="target_start must be inside the audit programme period")
    if end and end > programme.period_end:
        raise HTTPException(status_code=422, detail="target_end must be inside the audit programme period")


def _hybrid_signal_map(
    db: Session,
    amo_id: str,
    universe_items: list[QualityAuditUniverseItem],
) -> dict[str, dict[str, Any]]:
    """Build area-specific pressure from governed programme/audit lineage in bounded queries."""

    universe_by_id = {str(item.id): item for item in universe_items}
    signals: dict[str, dict[str, Any]] = {
        item_id: {
            "repeat_findings": 0,
            "open_findings": 0,
            "follow_up_required": 0,
            "deferred_audits": 0,
            "failed_controls": 0,
            "adverse_trends": 0,
            "last_audit_date": None,
        }
        for item_id in universe_by_id
    }
    if not universe_by_id:
        return signals

    history = db.query(QualityAuditProgrammeItem).filter(
        QualityAuditProgrammeItem.amo_id == amo_id,
        QualityAuditProgrammeItem.universe_item_id.in_(list(universe_by_id)),
    ).all()
    schedule_to_universe: dict[str, str] = {}
    programme_item_to_universe: dict[str, str] = {}
    for item in history:
        universe_id = str(item.universe_item_id)
        if universe_id not in signals:
            continue
        if item.state == "FOLLOW_UP_REQUIRED":
            signals[universe_id]["follow_up_required"] += 1
        if item.state == "DEFERRED":
            signals[universe_id]["deferred_audits"] += 1
        if item.schedule_id:
            schedule_to_universe[str(item.schedule_id)] = universe_id
        programme_item_to_universe[str(item.id)] = universe_id

    if programme_item_to_universe:
        occurrence_links = db.query(QualityAuditProgrammeOccurrenceLink).filter(
            QualityAuditProgrammeOccurrenceLink.amo_id == amo_id,
            QualityAuditProgrammeOccurrenceLink.programme_item_id.in_(list(programme_item_to_universe)),
        ).all()
        for link in occurrence_links:
            universe_id = programme_item_to_universe.get(str(link.programme_item_id))
            if universe_id:
                schedule_to_universe[str(link.schedule_id)] = universe_id

    audit_to_universe: dict[str, set[str]] = defaultdict(set)
    if schedule_to_universe:
        metadata = db.query(QMSPlannerScheduleMetadata).filter(
            QMSPlannerScheduleMetadata.amo_id == amo_id,
            QMSPlannerScheduleMetadata.source_schedule_id.in_(list(schedule_to_universe)),
            QMSPlannerScheduleMetadata.audit_id.isnot(None),
        ).all()
        for occurrence in metadata:
            universe_id = schedule_to_universe.get(str(occurrence.source_schedule_id))
            if not universe_id or not occurrence.audit_id:
                continue
            audit_to_universe[str(occurrence.audit_id)].add(universe_id)
            occurrence_date = occurrence.occurrence_date
            if occurrence_date and (
                signals[universe_id]["last_audit_date"] is None
                or occurrence_date > signals[universe_id]["last_audit_date"]
            ):
                signals[universe_id]["last_audit_date"] = occurrence_date

    requirement_refs: dict[str, Counter[str]] = defaultdict(Counter)
    if audit_to_universe:
        findings = db.query(models.QMSAuditFinding).filter(
            models.QMSAuditFinding.amo_id == amo_id,
            models.QMSAuditFinding.audit_id.in_(list(audit_to_universe)),
        ).all()
        for finding in findings:
            for universe_id in audit_to_universe.get(str(finding.audit_id), set()):
                if finding.closed_at is None:
                    signals[universe_id]["open_findings"] += 1
                if bool(getattr(finding, "safety_sensitive", False)):
                    signals[universe_id]["adverse_trends"] += 1
                ref = str(getattr(finding, "requirement_ref", "") or "").strip().upper()
                if ref:
                    requirement_refs[universe_id][ref] += 1
        for universe_id, counts in requirement_refs.items():
            signals[universe_id]["repeat_findings"] = sum(max(0, count - 1) for count in counts.values())

    source_index: dict[tuple[str, str], str] = {
        (str(item.source_type).upper(), str(item.source_id)): str(item.id)
        for item in universe_items
    }
    intelligence = db.query(QualityIntelligenceReview).filter(
        QualityIntelligenceReview.amo_id == amo_id,
        QualityIntelligenceReview.status.in_(["PROPOSED", "ACCEPTED"]),
    ).order_by(QualityIntelligenceReview.created_at.desc()).limit(500).all()
    for insight in intelligence:
        payload = insight.payload if isinstance(insight.payload, dict) else {}
        universe_id = str(payload.get("universe_item_id") or "") or None
        if universe_id not in signals:
            source_type = str(payload.get("source_type") or "").upper()
            source_id = str(payload.get("source_id") or "")
            universe_id = source_index.get((source_type, source_id))
        if not universe_id or universe_id not in signals:
            continue
        insight_type = str(insight.insight_type or "").upper()
        if "CONTROL" in insight_type and ("FAIL" in insight_type or "INEFFECT" in insight_type):
            signals[universe_id]["failed_controls"] += 1
        if str(insight.risk_level or "").upper() in {"HIGH", "CRITICAL"}:
            signals[universe_id]["adverse_trends"] += 1

    return signals


def _recurrence_for_interval(days: int) -> tuple[str, int | None]:
    if days <= 35:
        return "MONTHLY", None
    if days <= 100:
        return "QUARTERLY", None
    if days <= 200:
        return "SEMI_ANNUAL", None
    if days <= 370:
        return "ANNUAL", None
    return "CUSTOM", days


def _audit_type_for_entity(entity_type: str) -> str:
    return {
        "AIRCRAFT": "PRODUCT",
        "AIRCRAFT_TYPE": "PRODUCT",
        "SUPPLIER": "SUPPLIER",
        "CONTRACTOR": "CONTRACTED_FUNCTION",
        "FACILITY": "FACILITY",
        "STATION": "FACILITY",
        "PERSONNEL_GROUP": "PERSONNEL",
        "CAPABILITY": "TECHNICAL",
        "APPROVAL_RATING": "TECHNICAL",
        "DEPARTMENT": "DEPARTMENTAL",
        "PROCESS": "PROCESS",
    }.get(entity_type, "INTERNAL")


def _optimizer_payload(db: Session, programme: QualityAuditProgramme) -> dict[str, Any]:
    universe_kind = "INTERNAL" if programme.programme_kind == "INTERNAL" else "EXTERNAL"
    universe = db.query(QualityAuditUniverseItem).filter(
        QualityAuditUniverseItem.amo_id == programme.amo_id,
        QualityAuditUniverseItem.active.is_(True),
        or_(
            QualityAuditUniverseItem.programme_kind == universe_kind,
            QualityAuditUniverseItem.programme_kind == "BOTH",
        ),
    ).order_by(QualityAuditUniverseItem.display_label.asc()).limit(500).all()
    signal_map = _hybrid_signal_map(db, programme.amo_id, universe)
    covered = {str(item.universe_item_id): item for item in list(programme.items or []) if item.state != "CANCELLED"}
    recommendations: list[dict[str, Any]] = []

    for universe_item in universe:
        universe_id = str(universe_item.id)
        raw_signals = signal_map.get(universe_id, {})
        scoring_signals = {key: int(raw_signals.get(key, 0) or 0) for key in (
            "repeat_findings", "open_findings", "follow_up_required", "deferred_audits", "failed_controls", "adverse_trends"
        )}
        score = score_surveillance(universe_item=universe_item, signals=scoring_signals)
        last_audit_date = raw_signals.get("last_audit_date")
        interval_days = int(score["recommended_interval_days"])
        next_due = last_audit_date + timedelta(days=interval_days) if last_audit_date else None
        due_in_period = next_due is None or next_due <= programme.period_end
        recommended = bool(score["recommend_in_programme"] and due_in_period)

        if next_due and next_due >= programme.period_start:
            target_start = max(programme.period_start, next_due - timedelta(days=14))
            target_end = min(programme.period_end, next_due + timedelta(days=14))
        else:
            target_start, target_end = recommended_window(
                programme_start=programme.period_start,
                programme_end=programme.period_end,
                stable_key=f"{programme.programme_series}:{universe_id}:{ALGORITHM_VERSION}",
                priority_score=int(score["priority_score"]),
            )
        existing = covered.get(universe_id)
        recommendations.append({
            "universe_item_id": universe_id,
            "auditable_entity": universe_item.display_label,
            "entity_type": universe_item.entity_type,
            "source_route": universe_item.source_route,
            **score,
            "signals": {
                **scoring_signals,
                "last_audit_date": last_audit_date.isoformat() if last_audit_date else None,
            },
            "next_recommended_due": next_due.isoformat() if next_due else target_start.isoformat(),
            "target_start": target_start.isoformat(),
            "target_end": target_end.isoformat(),
            "recommended_in_current_programme": recommended,
            "in_programme": existing is not None,
            "programme_item_id": str(existing.id) if existing else None,
            "requires_amendment": bool(recommended and existing is None and programme.status in {"APPROVED", "ACTIVE"}),
        })

    recommendations.sort(key=lambda item: (-int(item["priority_score"]), item["auditable_entity"].lower()))
    mandatory_due = [item for item in recommendations if item["mandatory_baseline"] and item["recommended_in_current_programme"]]
    mandatory_gaps = [item for item in mandatory_due if not item["in_programme"]]
    adaptive = [item for item in recommendations if item["recommended_in_current_programme"] and not item["mandatory_baseline"]]
    gaps = [item for item in recommendations if item["recommended_in_current_programme"] and not item["in_programme"]]
    return {
        "algorithm": ALGORITHM_VERSION,
        "weights": WEIGHTS,
        "as_of": _utcnow().isoformat(),
        "assurance_model": "HYBRID",
        "continuous_monitoring_enabled": bool(programme.continuous_monitoring_enabled),
        "recommendations": recommendations,
        "summary": {
            "auditable_entities": len(universe),
            "recommended_current_period": sum(1 for item in recommendations if item["recommended_in_current_programme"]),
            "mandatory_baseline_due": len(mandatory_due),
            "mandatory_coverage_gaps": len(mandatory_gaps),
            "adaptive_risk_performance_coverage": len(adaptive),
            "coverage_gaps": len(gaps),
            "requires_amendment": sum(1 for item in gaps if item["requires_amendment"]),
        },
    }


def _sync_hybrid_recommendations(
    db: Session,
    programme: QualityAuditProgramme,
    ctx: TenantContext,
) -> dict[str, Any]:
    _assert_editable(programme)
    optimizer = _optimizer_payload(db, programme)
    existing = {
        str(item.universe_item_id): item
        for item in list(programme.items or [])
        if item.state != "CANCELLED"
    }
    # Soft-cancelled coverage stays omitted so rebuild does not resurrect removals.
    omitted_universe_ids = {
        str(item.universe_item_id)
        for item in list(programme.items or [])
        if item.state == "CANCELLED"
    }
    added = 0
    updated = 0
    now = _utcnow()

    for recommendation in optimizer["recommendations"]:
        if not recommendation["recommended_in_current_programme"]:
            continue
        universe_id = recommendation["universe_item_id"]
        universe = db.query(QualityAuditUniverseItem).filter(
            QualityAuditUniverseItem.amo_id == ctx.amo_id,
            QualityAuditUniverseItem.id == universe_id,
        ).first()
        if universe is None:
            continue
        recurrence, custom_interval = _recurrence_for_interval(int(recommendation["recommended_interval_days"]))
        target_start = date.fromisoformat(recommendation["target_start"])
        target_end = date.fromisoformat(recommendation["target_end"])
        hybrid_basis = {
            "driver": "HYBRID_ASSURANCE",
            "algorithm": recommendation["algorithm"],
            "priority_score": recommendation["priority_score"],
            "priority_band": recommendation["priority_band"],
            "components": recommendation["components"],
            "signals": recommendation["signals"],
            "recommended_interval_days": recommendation["recommended_interval_days"],
            "drivers": recommendation["drivers"],
            "evaluated_at": optimizer["as_of"],
        }
        row = existing.get(universe_id)
        if row is None:
            if universe_id in omitted_universe_ids:
                continue
            row = QualityAuditProgrammeItem(
                amo_id=ctx.amo_id,
                programme_id=programme.id,
                universe_item_id=universe.id,
                audit_type=_audit_type_for_entity(universe.entity_type),
                title=f"{universe.display_label} assurance audit",
                purpose="Continuous hybrid assurance coverage generated from compliance obligations, risk exposure and performance history.",
                scope=universe.display_label,
                criteria=list(programme.regulatory_basis or []),
                mandatory_surveillance=bool(universe.mandatory_surveillance),
                recurrence=recurrence,
                custom_interval_days=custom_interval,
                target_start=target_start,
                target_end=target_end,
                state="PLANNED",
                prioritization_basis=[hybrid_basis],
                created_by_user_id=ctx.user_id,
                updated_by_user_id=ctx.user_id,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            existing[universe_id] = row
            added += 1
            _event(
                db, programme, ctx, "ITEM_ADDED",
                f"Hybrid assurance engine added {row.title} at priority {recommendation['priority_score']}.",
                None,
                {"item_id": str(row.id), "universe_item_id": universe_id, "optimizer": hybrid_basis},
            )
            continue

        preserved = [
            basis for basis in list(row.prioritization_basis or [])
            if str(basis.get("driver") if isinstance(basis, dict) else "") != "HYBRID_ASSURANCE"
        ]
        before = {
            "target_start": row.target_start.isoformat() if row.target_start else None,
            "target_end": row.target_end.isoformat() if row.target_end else None,
            "recurrence": row.recurrence,
            "mandatory_surveillance": row.mandatory_surveillance,
        }
        changed = False
        row.prioritization_basis = [*preserved, hybrid_basis]
        if bool(universe.mandatory_surveillance) and not row.mandatory_surveillance:
            row.mandatory_surveillance = True
            changed = True
        current_interval = row.custom_interval_days if row.recurrence == "CUSTOM" else {
            "MONTHLY": 31, "QUARTERLY": 92, "SEMI_ANNUAL": 183, "ANNUAL": 365, "ONE_TIME": 3650,
        }.get(row.recurrence, 3650)
        if row.recurrence != "FIXED_DATES" and int(recommendation["recommended_interval_days"]) < int(current_interval or 3650):
            row.recurrence = recurrence
            row.custom_interval_days = custom_interval
            changed = True
        if row.recurrence != "FIXED_DATES" and (row.target_start is None or target_start < row.target_start):
            row.target_start = target_start
            changed = True
        if row.recurrence != "FIXED_DATES" and (row.target_end is None or target_end < row.target_end):
            row.target_end = max(row.target_start or target_start, target_end)
            changed = True
        row.updated_by_user_id = ctx.user_id
        row.updated_at = now
        if changed:
            updated += 1
            _event(
                db, programme, ctx, "ITEM_UPDATED",
                f"Hybrid assurance engine increased surveillance for {row.title} to priority {recommendation['priority_score']}.",
                before,
                {"target_start": row.target_start.isoformat() if row.target_start else None,
                 "target_end": row.target_end.isoformat() if row.target_end else None,
                 "recurrence": row.recurrence, "optimizer": hybrid_basis},
            )

    db.flush()
    programme.updated_by_user_id = ctx.user_id
    programme.updated_at = now
    refreshed = _optimizer_payload(db, programme)
    refreshed["sync"] = {"added": added, "updated": updated}
    return refreshed


def _date_in_year(value: date | None, year: int) -> date | None:
    if value is None:
        return None
    try:
        return value.replace(year=year)
    except ValueError:
        return value.replace(year=year, day=28)


_CARRY_FORWARD_STATUS_RANK = {
    "ACTIVE": 0,
    "APPROVED": 1,
    "SUPERSEDED": 2,
    "DRAFT": 3,
    "UNDER_REVIEW": 4,
}


def _select_carry_forward_source(
    candidates: list[QualityAuditProgramme],
) -> QualityAuditProgramme | None:
    """Prefer published prior-year programmes; still allow draft planning roll-forward."""
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda row: (
            _CARRY_FORWARD_STATUS_RANK.get(str(row.status or "").upper(), 99),
            -int(row.revision_no or 0),
            -(row.updated_at.timestamp() if row.updated_at else 0.0),
        ),
    )


def _carry_forward_previous_year(
    db: Session,
    *,
    programme: QualityAuditProgramme,
    ctx: TenantContext,
) -> int:
    candidates = (
        _query(db, ctx.amo_id)
        .options(selectinload(QualityAuditProgramme.items))
        .filter(
            QualityAuditProgramme.programme_year == programme.programme_year - 1,
            QualityAuditProgramme.programme_kind == programme.programme_kind,
            QualityAuditProgramme.status.in_(
                ("ACTIVE", "APPROVED", "SUPERSEDED", "DRAFT", "UNDER_REVIEW"),
            ),
        )
        .all()
    )
    previous = _select_carry_forward_source(list(candidates))
    if previous is None:
        return 0
    if not list(programme.objectives or []):
        programme.objectives = list(previous.objectives or [])
    if not list(programme.regulatory_basis or []):
        programme.regulatory_basis = list(previous.regulatory_basis or [])
    now = _utcnow()
    copied = 0
    for source in list(previous.items or []):
        if source.state == "CANCELLED":
            continue
        preserved_basis = [
            basis
            for basis in list(source.prioritization_basis or [])
            if not (
                isinstance(basis, dict)
                and str(basis.get("driver") or "").upper() == "HYBRID_ASSURANCE"
            )
        ]
        data: dict[str, Any] = {
            "amo_id": ctx.amo_id,
            "programme_id": programme.id,
            "universe_item_id": source.universe_item_id,
            "audit_type": source.audit_type,
            "title": source.title,
            "purpose": source.purpose,
            "scope": source.scope,
            "criteria": list(source.criteria or []),
            "mandatory_surveillance": source.mandatory_surveillance,
            "recurrence": source.recurrence,
            "custom_interval_days": source.custom_interval_days,
            "fixed_dates": list(source.fixed_dates or []),
            "non_working_day_policy": source.non_working_day_policy,
            "default_start_time": source.default_start_time,
            "default_end_time": source.default_end_time,
            "default_duration_days": source.default_duration_days,
            "default_location": source.default_location,
            "lead_auditor_user_id": source.lead_auditor_user_id,
            "observer_auditor_user_id": source.observer_auditor_user_id,
            "supporting_auditor_user_ids": list(source.supporting_auditor_user_ids or []),
            "auditee_user_id": source.auditee_user_id,
            "notify_auditors": source.notify_auditors,
            "notify_auditees": source.notify_auditees,
            "auto_schedule": source.auto_schedule,
            "target_start": _date_in_year(source.target_start, programme.programme_year),
            "target_end": _date_in_year(source.target_end, programme.programme_year),
            "state": "PLANNED",
            "prioritization_basis": [
                *preserved_basis,
                {"driver": "ANNUAL_CARRY_FORWARD", "source_programme_id": str(previous.id)},
            ],
            "created_by_user_id": ctx.user_id,
            "updated_by_user_id": ctx.user_id,
            "created_at": now,
            "updated_at": now,
        }
        if source.recurrence == "FIXED_DATES":
            _apply_fixed_date_window(programme, data)
        elif data["target_start"] and data["target_end"]:
            _validate_item_window(programme, data["target_start"], data["target_end"])
        db.add(QualityAuditProgrammeItem(**data))
        copied += 1
    if copied:
        _event(
            db,
            programme,
            ctx,
            "ITEM_ADDED",
            f"Carried forward {copied} governed audit requirement(s) from {previous.programme_year} for annual review.",
            None,
            {"source_programme_id": str(previous.id), "copied_count": copied},
        )
    return copied


def _pick_rotated_assignee(
    *,
    pool: list[str],
    exclude: set[str],
    previous: str | None,
    load: Counter[str],
) -> str | None:
    """Pick a rotated assignee. Returns None when the pool cannot supply a replacement."""
    candidates = [user_id for user_id in pool if user_id not in exclude]
    if not candidates:
        return None
    preferred = (
        [user_id for user_id in candidates if user_id != previous]
        if previous and len(candidates) > 1
        else list(candidates)
    )
    if not preferred:
        preferred = list(candidates)
    preferred.sort(key=lambda user_id: (int(load[user_id]), user_id))
    min_load = int(load[preferred[0]])
    tied = [user_id for user_id in preferred if int(load[user_id]) == min_load]
    choice = random.choice(tied)
    load[choice] += 1
    return choice


def _auditor_assignment_pools(
    db: Session,
    *,
    amo_id: str,
) -> tuple[list[str], list[str], list[str]]:
    from .planner_schedule_router import _auditor_roles_by_user

    roles_by_user = _auditor_roles_by_user(db, amo_id=amo_id)
    lead_pool = sorted(
        user_id for user_id, roles in roles_by_user.items() if "LEAD_AUDITOR" in roles
    )
    observer_pool = sorted(
        user_id for user_id, roles in roles_by_user.items() if "OBSERVER_AUDITOR" in roles
    )
    supporting_pool = sorted(roles_by_user.keys())
    return lead_pool, observer_pool, supporting_pool


def _rotate_carried_auditors(
    db: Session,
    *,
    programme: QualityAuditProgramme,
    ctx: TenantContext,
) -> int:
    """Randomly reassign carried auditor slots from the live privilege pools."""
    items = [
        item
        for item in list(programme.items or [])
        if str(item.state or "").upper() != "CANCELLED"
    ]
    if not items:
        db.refresh(programme, attribute_names=["items"])
        items = [
            item
            for item in list(programme.items or [])
            if str(item.state or "").upper() != "CANCELLED"
        ]
    if not items:
        items = (
            db.query(QualityAuditProgrammeItem)
            .filter(
                QualityAuditProgrammeItem.amo_id == ctx.amo_id,
                QualityAuditProgrammeItem.programme_id == programme.id,
                QualityAuditProgrammeItem.state != "CANCELLED",
            )
            .all()
        )
    if not items:
        return 0

    lead_pool, observer_pool, supporting_pool = _auditor_assignment_pools(
        db, amo_id=ctx.amo_id
    )
    lead_load: Counter[str] = Counter()
    observer_load: Counter[str] = Counter()
    supporting_load: Counter[str] = Counter()
    rotated = 0
    now = _utcnow()

    for item in items:
        previous_lead = str(item.lead_auditor_user_id or "").strip() or None
        previous_observer = str(item.observer_auditor_user_id or "").strip() or None
        previous_supporting = [
            str(user_id).strip()
            for user_id in list(item.supporting_auditor_user_ids or [])
            if str(user_id).strip()
        ]
        auditee = str(item.auditee_user_id or "").strip() or None
        blocked = {auditee} if auditee else set()

        next_lead = previous_lead
        if previous_lead:
            picked = _pick_rotated_assignee(
                pool=lead_pool,
                exclude=blocked,
                previous=previous_lead,
                load=lead_load,
            )
            if picked:
                next_lead = picked

        next_observer = previous_observer
        if previous_observer:
            observer_blocked = set(blocked)
            if next_lead:
                observer_blocked.add(next_lead)
            picked = _pick_rotated_assignee(
                pool=observer_pool,
                exclude=observer_blocked,
                previous=previous_observer,
                load=observer_load,
            )
            if picked:
                next_observer = picked

        next_supporting = list(previous_supporting)
        if previous_supporting:
            supporting_blocked = set(blocked)
            if next_lead:
                supporting_blocked.add(next_lead)
            if next_observer:
                supporting_blocked.add(next_observer)
            assigned: list[str] = []
            for previous in previous_supporting:
                picked = _pick_rotated_assignee(
                    pool=supporting_pool,
                    exclude=supporting_blocked | set(assigned),
                    previous=previous,
                    load=supporting_load,
                )
                if picked:
                    assigned.append(picked)
                    supporting_blocked.add(picked)
                else:
                    # Keep prior when pool cannot fill this slot.
                    if previous not in supporting_blocked and previous not in assigned:
                        assigned.append(previous)
                        supporting_blocked.add(previous)
            next_supporting = _normalise_supporting_auditors(
                assigned,
                lead_auditor_user_id=next_lead,
                observer_auditor_user_id=next_observer,
            )

        if (
            next_lead == previous_lead
            and next_observer == previous_observer
            and next_supporting == previous_supporting
        ):
            continue

        try:
            _validate_item_auditor_privileges(
                db,
                amo_id=ctx.amo_id,
                lead_user_id=next_lead,
                observer_user_id=next_observer,
                supporting_user_ids=next_supporting,
            )
        except HTTPException:
            continue

        item.lead_auditor_user_id = next_lead
        item.observer_auditor_user_id = next_observer
        item.supporting_auditor_user_ids = next_supporting
        item.updated_by_user_id = ctx.user_id
        item.updated_at = now
        rotated += 1

    if rotated:
        _event(
            db,
            programme,
            ctx,
            "ITEM_UPDATED",
            f"Rotated auditor assignments on {rotated} carried audit(s) for annual review.",
            None,
            {"rotated_count": rotated},
        )
    return rotated


@router.get("")
def list_programmes(
    year: int | None = Query(default=None, ge=2000, le=2200),
    status_filter: ProgrammeStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")), db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = _query(db, ctx.amo_id).options(
        selectinload(QualityAuditProgramme.items).selectinload(QualityAuditProgrammeItem.universe_item)
    )
    if year is not None:
        query = query.filter(QualityAuditProgramme.programme_year == year)
    if status_filter:
        query = query.filter(QualityAuditProgramme.status == status_filter)
    total = int(query.order_by(None).count())
    rows = query.order_by(QualityAuditProgramme.programme_year.desc(), QualityAuditProgramme.revision_no.desc()).offset(offset).limit(limit).all()
    return {"items": [_programme_dict(row) for row in rows], "total": total, "limit": limit, "offset": offset,
            "has_more": offset + len(rows) < total}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_programme(payload: ProgrammeCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    owner_user_id = payload.owner_user_id or ctx.user_id
    _validate_programme_owner(db, amo_id=ctx.amo_id, user_id=owner_user_id)
    _assert_programme_kind_available(db, amo_id=ctx.amo_id, year=payload.programme_year, kind=payload.programme_kind)
    title = (payload.title or _programme_kind_title(payload.programme_kind, payload.programme_year)).strip()
    ref, series = _programme_ref(payload.programme_year, 1)
    now = _utcnow()
    row = QualityAuditProgramme(
        amo_id=ctx.amo_id, programme_ref=ref, programme_series=series, programme_year=payload.programme_year,
        programme_kind=payload.programme_kind, revision_no=1, title=title, continuous_monitoring_enabled=True,
        optimizer_version=ALGORITHM_VERSION, objectives=payload.objectives,
        regulatory_basis=payload.regulatory_basis, status="DRAFT", period_start=payload.period_start,
        period_end=payload.period_end, owner_user_id=owner_user_id,
        created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id, created_at=now, updated_at=now,
    )
    db.add(row)
    db.flush()
    _event(
        db,
        row,
        ctx,
        "CREATED",
        (
            "Hybrid-seeded audit programme created."
            if payload.apply_hybrid_seed
            else "Audit programme draft created."
        ),
        None,
        _programme_snapshot(row),
    )
    _ensure_standard_audit_areas(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id)
    copied = 0
    if payload.copy_previous_year:
        copied = _carry_forward_previous_year(db, programme=row, ctx=ctx)
    if payload.rotate_auditors and copied:
        db.flush()
        _rotate_carried_auditors(db, programme=row, ctx=ctx)
    if payload.apply_hybrid_seed:
        _sync_hybrid_recommendations(db, row, ctx)
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, str(row.id)), detail=True)


@router.get("/{programme_id}/optimizer")
def get_programme_optimizer(programme_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")), db: Session = Depends(get_read_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme = _load_programme(db, ctx.amo_id, programme_id)
    return _optimizer_payload(db, programme)


@router.post("/{programme_id}/optimizer/rebuild")
def rebuild_programme_optimizer(programme_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme = _load_programme(db, ctx.amo_id, programme_id, for_update=True)
    if programme.status == "DRAFT":
        result = _sync_hybrid_recommendations(db, programme, ctx)
        db.commit()
        return result
    result = _optimizer_payload(db, programme)
    result["sync"] = {"added": 0, "updated": 0}
    result["governance"] = {
        "programme_immutable": True,
        "message": "New adaptive coverage requires an amendment revision; the optimizer does not silently rewrite an approved programme.",
    }
    return result


def _programme_people(db: Session, programme: QualityAuditProgramme) -> dict[str, str]:
    user_ids = {
        str(value)
        for value in (
            programme.owner_user_id,
            programme.submitted_by_user_id,
            programme.quality_reviewed_by_user_id,
            programme.approved_by_user_id,
        )
        if value
    }
    for item in list(programme.items or []):
        user_ids.update(str(value) for value in (
            item.lead_auditor_user_id,
            item.observer_auditor_user_id,
            item.auditee_user_id,
            *list(item.supporting_auditor_user_ids or []),
        ) if value)
    if not user_ids:
        return {}
    rows = db.query(account_models.User).filter(
        account_models.User.amo_id == programme.amo_id,
        account_models.User.id.in_(user_ids),
    ).all()
    return {str(user.id): str(user.full_name or user.email or user.id) for user in rows}


def _programme_timezone(db: Session, programme: QualityAuditProgramme) -> str:
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == programme.amo_id).first()
    return str(getattr(amo, "time_zone", None) or "UTC")


def _assert_exportable(programme: QualityAuditProgramme, *, allow_draft: bool = False) -> None:
    controlled = {"APPROVED", "ACTIVE", "SUPERSEDED", "CLOSED"}
    draft_ok = {"DRAFT", "UNDER_REVIEW"}
    allowed = controlled | (draft_ok if allow_draft else set())
    if programme.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The controlled schedule becomes downloadable after Accountable Executive approval.",
        )


@router.get("/{programme_id}/schedule.pdf")
def export_programme_pdf(
    programme_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.reports.export")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme = _load_programme(db, ctx.amo_id, programme_id)
    _assert_exportable(programme, allow_draft=True)
    draft = programme.status in {"DRAFT", "UNDER_REVIEW"}
    content = audit_programme_pdf(programme, _programme_people(db, programme), draft=draft)
    filename = f"{programme.programme_ref.replace('/', '-')}-audit-schedule.pdf"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{programme_id}/schedule.ics")
def export_programme_calendar(
    programme_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.reports.export")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme = _load_programme(db, ctx.amo_id, programme_id)
    _assert_exportable(programme)
    content = audit_programme_ics(
        programme,
        _programme_people(db, programme),
        _programme_timezone(db, programme),
    )
    filename = f"{programme.programme_ref.replace('/', '-')}-audit-schedule.ics"
    return Response(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store"},
    )


@router.get("/{programme_id}")
def get_programme(programme_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")), db: Session = Depends(get_read_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, programme_id), detail=True)


@router.patch("/{programme_id}")
def patch_programme(programme_id: str, payload: ProgrammePatch,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _load_programme(db, ctx.amo_id, programme_id, for_update=True)
    _assert_editable(row)
    before = _programme_snapshot(row)
    updates = payload.model_dump(exclude_unset=True, exclude={"reason"})
    if "owner_user_id" in updates:
        _validate_programme_owner(db, amo_id=ctx.amo_id, user_id=updates["owner_user_id"])
    for field, value in updates.items():
        setattr(row, field, value)
    if row.period_end < row.period_start:
        raise HTTPException(status_code=422, detail="period_end must be on or after period_start")
    if row.period_start.year != row.programme_year or row.period_end.year != row.programme_year:
        raise HTTPException(status_code=422, detail="The programme period must stay within its calendar year.")
    for item in list(row.items or []):
        if item.recurrence == "FIXED_DATES":
            candidate = {
                "recurrence": item.recurrence,
                "fixed_dates": list(item.fixed_dates or []),
                "default_duration_days": item.default_duration_days,
            }
            _apply_fixed_date_window(row, candidate)
            item.target_start = candidate["target_start"]
            item.target_end = candidate["target_end"]
        else:
            _validate_item_window(row, item.target_start, item.target_end)
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    _event(db, row, ctx, "UPDATED", payload.reason, before, _programme_snapshot(row))
    # Do not silently re-seed hybrid coverage on metadata edits — that produced
    # unexplained audits/scores on draft programmes. Seed only via explicit create
    # flag or the optimizer rebuild action.
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, programme_id), detail=True)


_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"UNDER_REVIEW", "CLOSED"},
    "UNDER_REVIEW": {"DRAFT", "APPROVED"},
    "APPROVED": {"ACTIVE", "SUPERSEDED"},
    "ACTIVE": {"SUPERSEDED", "CLOSED"},
    "SUPERSEDED": set(),
    "CLOSED": set(),
}
_EVENT_BY_TARGET = {"UNDER_REVIEW": "SUBMITTED_FOR_REVIEW", "DRAFT": "RETURNED_TO_DRAFT", "APPROVED": "APPROVED",
                    "ACTIVE": "ACTIVATED", "SUPERSEDED": "SUPERSEDED", "CLOSED": "CLOSED"}


@router.post("/{programme_id}/transitions")
def transition_programme(programme_id: str, payload: ProgrammeTransition, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _load_programme(db, ctx.amo_id, programme_id, for_update=True)
    if payload.target_status == "APPROVED":
        assert_quality_permission(db, ctx, "qms.audit.programme.approve")
    elif payload.target_status == "DRAFT" and row.status == "UNDER_REVIEW":
        assert_quality_permission(
            db,
            ctx,
            "qms.audit.programme.approve" if row.quality_reviewed_at else "qms.audit.programme.quality_review",
        )
    else:
        assert_quality_permission(db, ctx, "qms.audit.manage")
    if payload.target_status not in _TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=409, detail=f"Audit programme cannot transition from {row.status} to {payload.target_status}.")
    if payload.target_status == "UNDER_REVIEW" and not _active_programme_role_users(
        db,
        amo_id=ctx.amo_id,
        role_name="QUALITY_MANAGER",
        exclude_user_id=ctx.user_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assign a different active Quality Manager before submitting this programme for independent review.",
        )
    if payload.target_status in {"UNDER_REVIEW", "APPROVED"}:
        optimizer = _optimizer_payload(db, row)
        readiness = _programme_readiness(row, mandatory_coverage_gaps=int(optimizer["summary"]["mandatory_coverage_gaps"]))
        if not readiness["ready_for_approval"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Audit programme is not ready for the approval workflow.", "blockers": readiness["blockers"]},
            )
    if payload.target_status == "APPROVED" and not row.quality_reviewed_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quality Manager review must be recorded before Accountable Executive approval.",
        )
    before = _programme_snapshot(row)
    now = _utcnow()
    row.status = payload.target_status
    if row.status == "UNDER_REVIEW":
        row.submitted_by_user_id = ctx.user_id
        row.submitted_at = now
        row.quality_reviewed_by_user_id = None
        row.quality_reviewed_at = None
    if row.status == "DRAFT":
        row.submitted_by_user_id = None
        row.submitted_at = None
        row.quality_reviewed_by_user_id = None
        row.quality_reviewed_at = None
    if row.status == "APPROVED":
        row.approved_by_user_id = ctx.user_id
        row.approved_at = now
    if row.status == "ACTIVE":
        row.activated_at = now
    if row.status == "CLOSED":
        row.closed_at = now
    row.updated_by_user_id = ctx.user_id
    row.updated_at = now
    schedule_generation: dict[str, Any] | None = None
    if row.status == "ACTIVE":
        from .audit_programme_schedule_router import materialize_fixed_date_programme

        schedule_generation = materialize_fixed_date_programme(
            db=db,
            programme=row,
            request=request,
            ctx=ctx,
        )
    after = _programme_snapshot(row)
    if schedule_generation is not None:
        after["schedule_generation"] = schedule_generation
    _event(db, row, ctx, _EVENT_BY_TARGET[row.status], payload.reason, before, after)
    if row.status == "UNDER_REVIEW":
        _notify_programme_users(
            db,
            programme=row,
            ctx=ctx,
            role_names=("QUALITY_MANAGER",),
            message=f"{row.programme_ref} is ready for Quality Manager review. {payload.reason.strip()}",
            subject=f"Quality review required · {row.programme_ref}",
            template_key="qms_audit_programme_quality_review_required",
            correlation_suffix=f"submitted:{row.submitted_at.isoformat()}",
            action_required=True,
        )
    elif row.status == "DRAFT":
        _notify_programme_users(
            db,
            programme=row,
            ctx=ctx,
            extra_user_ids=(before.get("submitted_by_user_id"), row.owner_user_id),
            message=f"{row.programme_ref} was returned to draft. {payload.reason.strip()}",
            subject=f"Programme changes required · {row.programme_ref}",
            template_key="qms_audit_programme_returned",
            correlation_suffix=f"returned:{now.isoformat()}",
            action_required=True,
        )
    elif row.status == "APPROVED":
        _notify_programme_users(
            db,
            programme=row,
            ctx=ctx,
            role_names=("QUALITY_MANAGER", "QUALITY_OFFICER"),
            extra_user_ids=(row.owner_user_id, row.submitted_by_user_id),
            message=f"{row.programme_ref} received Accountable Executive approval and is ready to publish. {payload.reason.strip()}",
            subject=f"Programme approved · {row.programme_ref}",
            template_key="qms_audit_programme_approved",
            correlation_suffix=f"approved:{now.isoformat()}",
            action_required=True,
        )
    elif row.status == "ACTIVE":
        _notify_programme_users(
            db,
            programme=row,
            ctx=ctx,
            extra_user_ids=(row.owner_user_id, row.submitted_by_user_id, row.quality_reviewed_by_user_id),
            message=f"{row.programme_ref} was published. Scheduled audit participants were notified and assigned events are available in calendar subscriptions.",
            subject=f"Programme published · {row.programme_ref}",
            template_key="qms_audit_programme_published",
            correlation_suffix=f"published:{now.isoformat()}",
            action_required=False,
        )
    if row.status == "APPROVED" and row.supersedes_programme_id:
        prior = _query(db, ctx.amo_id).filter(QualityAuditProgramme.id == row.supersedes_programme_id).with_for_update().first()
        if prior and prior.status in {"APPROVED", "ACTIVE"}:
            old_before = _programme_snapshot(prior)
            prior.status = "SUPERSEDED"
            prior.updated_by_user_id = ctx.user_id
            prior.updated_at = now
            _event(db, prior, ctx, "SUPERSEDED", f"Superseded by approved revision {row.programme_ref}.", old_before, _programme_snapshot(prior))
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, programme_id), detail=True)


@router.post("/{programme_id}/quality-review")
def quality_review_programme(
    programme_id: str,
    payload: ProgrammeQualityReview,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.programme.quality_review")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _load_programme(db, ctx.amo_id, programme_id, for_update=True)
    if row.status != "UNDER_REVIEW":
        raise HTTPException(status_code=409, detail="Only a submitted programme can receive Quality Manager review.")
    if payload.decision == "FORWARD" and row.quality_reviewed_at:
        raise HTTPException(status_code=409, detail="Quality Manager review is already recorded for this revision.")
    if payload.decision == "FORWARD" and str(row.submitted_by_user_id or "") == ctx.user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The person who submitted the programme cannot also record the independent Quality Manager review.",
        )
    before = _programme_snapshot(row)
    now = _utcnow()
    if payload.decision == "RETURN":
        submitted_by_user_id = row.submitted_by_user_id
        row.status = "DRAFT"
        row.submitted_by_user_id = None
        row.submitted_at = None
        row.quality_reviewed_by_user_id = None
        row.quality_reviewed_at = None
        event_type = "RETURNED_TO_DRAFT"
        recipients = (submitted_by_user_id, row.owner_user_id)
        notification_message = f"{row.programme_ref} was returned to draft by the Quality Manager. {payload.reason.strip()}"
        subject = f"Programme changes required · {row.programme_ref}"
        template_key = "qms_audit_programme_quality_review_returned"
        role_names: tuple[str, ...] = ()
    else:
        if not _active_programme_role_users(
            db,
            amo_id=ctx.amo_id,
            role_name="ACCOUNTABLE_EXECUTIVE",
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Assign an active Accountable Executive before forwarding this programme for final approval.",
            )
        optimizer = _optimizer_payload(db, row)
        readiness = _programme_readiness(row, mandatory_coverage_gaps=int(optimizer["summary"]["mandatory_coverage_gaps"]))
        if not readiness["ready_for_approval"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "The programme is no longer ready for Quality review.", "blockers": readiness["blockers"]},
            )
        row.quality_reviewed_by_user_id = ctx.user_id
        row.quality_reviewed_at = now
        event_type = "QUALITY_REVIEW_COMPLETED"
        recipients = ()
        notification_message = f"{row.programme_ref} passed Quality Manager review and requires Accountable Executive approval. {payload.reason.strip()}"
        subject = f"Executive approval required · {row.programme_ref}"
        template_key = "qms_audit_programme_executive_approval_required"
        role_names = ("ACCOUNTABLE_EXECUTIVE",)
    row.updated_by_user_id = ctx.user_id
    row.updated_at = now
    _event(db, row, ctx, event_type, payload.reason, before, _programme_snapshot(row))
    _notify_programme_users(
        db,
        programme=row,
        ctx=ctx,
        role_names=role_names,
        extra_user_ids=recipients,
        message=notification_message,
        subject=subject,
        template_key=template_key,
        correlation_suffix=f"quality-review:{payload.decision.lower()}:{now.isoformat()}",
        action_required=True,
    )
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, programme_id), detail=True)


@router.post("/{programme_id}/amendments", status_code=status.HTTP_201_CREATED)
def create_amendment(programme_id: str, payload: ProgrammeAmendment,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    prior = _load_programme(db, ctx.amo_id, programme_id, for_update=True)
    if prior.status not in {"APPROVED", "ACTIVE"}:
        raise HTTPException(status_code=409, detail="Only APPROVED or ACTIVE programme revisions can be amended.")
    existing = _query(db, ctx.amo_id).filter(QualityAuditProgramme.programme_series == prior.programme_series).order_by(QualityAuditProgramme.revision_no.desc()).first()
    next_revision = int(existing.revision_no) + 1
    now = _utcnow()
    row = QualityAuditProgramme(
        amo_id=ctx.amo_id, programme_ref=f"{prior.programme_series}-R{next_revision:02d}", programme_series=prior.programme_series,
        programme_year=prior.programme_year, programme_kind=prior.programme_kind,
        revision_no=next_revision, title=(payload.title or prior.title).strip(),
        continuous_monitoring_enabled=True, optimizer_version=ALGORITHM_VERSION,
        objectives=list(prior.objectives or []), regulatory_basis=list(prior.regulatory_basis or []), status="DRAFT",
        period_start=prior.period_start, period_end=prior.period_end, owner_user_id=prior.owner_user_id,
        supersedes_programme_id=prior.id, created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id,
        created_at=now, updated_at=now,
    )
    db.add(row)
    db.flush()
    for item in list(prior.items or []):
        db.add(QualityAuditProgrammeItem(
            amo_id=ctx.amo_id, programme_id=row.id, universe_item_id=item.universe_item_id, audit_type=item.audit_type,
            title=item.title, purpose=item.purpose, scope=item.scope, criteria=list(item.criteria or []),
            mandatory_surveillance=item.mandatory_surveillance, recurrence=item.recurrence,
            custom_interval_days=item.custom_interval_days, fixed_dates=list(item.fixed_dates or []),
            non_working_day_policy=item.non_working_day_policy,
            default_start_time=item.default_start_time, default_end_time=item.default_end_time,
            default_duration_days=item.default_duration_days, default_location=item.default_location,
            lead_auditor_user_id=item.lead_auditor_user_id,
            observer_auditor_user_id=item.observer_auditor_user_id,
            supporting_auditor_user_ids=list(item.supporting_auditor_user_ids or []),
            auditee_user_id=item.auditee_user_id,
            notify_auditors=item.notify_auditors, notify_auditees=item.notify_auditees,
            auto_schedule=item.auto_schedule, target_start=item.target_start, target_end=item.target_end,
            state="PLANNED", prioritization_basis=list(item.prioritization_basis or []),
            created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id, created_at=now, updated_at=now,
        ))
    db.flush()
    _event(db, row, ctx, "AMENDMENT_CREATED", payload.reason, _programme_snapshot(prior), _programme_snapshot(row))
    # Do not silently re-seed hybrid coverage on amendments — apply via explicit optimizer rebuild.
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _programme_dict(_load_programme(db, ctx.amo_id, str(row.id)), detail=True)


@router.get("/universe/items")
def list_universe(entity_type: EntityType | None = None, programme_kind: UniverseProgrammeKind | None = None,
    active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")), db: Session = Depends(get_read_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityAuditUniverseItem).filter(QualityAuditUniverseItem.amo_id == ctx.amo_id)
    if entity_type:
        query = query.filter(QualityAuditUniverseItem.entity_type == entity_type)
    if programme_kind:
        query = query.filter(or_(
            QualityAuditUniverseItem.programme_kind == programme_kind,
            QualityAuditUniverseItem.programme_kind == "BOTH",
        ))
    if active is not None:
        query = query.filter(QualityAuditUniverseItem.active.is_(active))
    total = int(query.order_by(None).count())
    rows = query.order_by(QualityAuditUniverseItem.display_label.asc()).offset(offset).limit(limit).all()
    aircraft_by_id = _aircraft_by_source_id(db, amo_id=ctx.amo_id, items=rows)
    return {"items": [_universe_dict(row, aircraft_by_id.get(str(row.source_id))) for row in rows], "total": total, "limit": limit, "offset": offset,
            "has_more": offset + len(rows) < total}


@router.post("/universe/ensure-defaults", status_code=status.HTTP_200_OK)
def ensure_universe_defaults(
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    created = _ensure_standard_audit_areas(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id)
    db.commit()
    total = db.query(QualityAuditUniverseItem.id).filter(
        QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.source_owner_module == "QUALITY_STANDARD",
    ).count()
    return {"created": created, "standard_area_count": int(total)}


@router.post("/universe/items", status_code=status.HTTP_201_CREATED)
def create_universe_item(payload: UniverseCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    duplicate = db.query(QualityAuditUniverseItem.id).filter(
        QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.source_owner_module == payload.source_owner_module,
        QualityAuditUniverseItem.source_type == payload.source_type,
        QualityAuditUniverseItem.source_id == payload.source_id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="This authoritative source record is already in the Audit Universe.")
    data = payload.model_dump()
    aircraft = None
    if payload.entity_type == "AIRCRAFT":
        if payload.source_owner_module != "FLEET" or payload.source_type != "AIRCRAFT":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Aircraft audit areas must be selected from this tenant's Fleet register.",
            )
        from amodb.apps.fleet.models import Aircraft

        aircraft = db.query(Aircraft).filter(
            Aircraft.amo_id == ctx.amo_id,
            Aircraft.serial_number == payload.source_id,
            Aircraft.is_active.is_(True),
        ).first()
        if aircraft is None:
            raise HTTPException(status_code=404, detail="The selected active aircraft was not found in this tenant's Fleet register.")
        model_label = aircraft.model or aircraft.aircraft_model_code or "Model not recorded"
        data["display_label"] = f"{aircraft.registration} · {model_label}"
        data["source_route"] = data.get("source_route") or f"/maintenance/{ctx.amo_code}/production/fleet/{aircraft.serial_number}"
    now = _utcnow()
    row = QualityAuditUniverseItem(
        amo_id=ctx.amo_id, **data, created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id,
        created_at=now, updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _universe_dict(row, aircraft)


@router.patch("/universe/items/{universe_item_id}")
def patch_universe_item(universe_item_id: str, payload: UniversePatch,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditUniverseItem).filter(QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.id == universe_item_id).with_for_update().first()
    if not row:
        raise HTTPException(status_code=404, detail="Audit Universe item not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return _universe_dict(row)


@router.post("/{programme_id}/items", status_code=status.HTTP_201_CREATED)
def add_programme_item(programme_id: str, payload: ProgrammeItemCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme = _load_programme(db, ctx.amo_id, programme_id, for_update=True)
    _assert_editable(programme)
    universe = db.query(QualityAuditUniverseItem).filter(QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.id == payload.universe_item_id, QualityAuditUniverseItem.active.is_(True)).first()
    if not universe:
        raise HTTPException(status_code=422, detail="Select an active Audit Universe item from this tenant.")
    programme_universe_kind = "INTERNAL" if programme.programme_kind == "INTERNAL" else "EXTERNAL"
    if universe.programme_kind not in {programme_universe_kind, "BOTH"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Select an audit area available to this {programme_universe_kind.lower()} programme.",
        )
    now = _utcnow()
    data = payload.model_dump()
    data["audit_type"] = _audit_type_for_entity(universe.entity_type)
    data["mandatory_surveillance"] = bool(payload.mandatory_surveillance or universe.mandatory_surveillance)
    _validate_item_people(
        db,
        amo_id=ctx.amo_id,
        user_ids=[
            payload.lead_auditor_user_id,
            payload.observer_auditor_user_id,
            payload.auditee_user_id,
            *payload.supporting_auditor_user_ids,
        ],
    )
    _validate_item_auditor_privileges(
        db,
        amo_id=ctx.amo_id,
        lead_user_id=payload.lead_auditor_user_id,
        observer_user_id=payload.observer_auditor_user_id,
        supporting_user_ids=payload.supporting_auditor_user_ids,
    )
    _validate_item_location(
        db,
        amo_id=ctx.amo_id,
        location_code=payload.default_location,
        required=universe.entity_type in {"FACILITY", "STATION"},
    )
    if payload.recurrence == "FIXED_DATES":
        _apply_fixed_date_window(programme, data)
    else:
        _validate_item_window(programme, payload.target_start, payload.target_end)
    row = QualityAuditProgrammeItem(
        amo_id=ctx.amo_id, programme_id=programme.id, **data, state="PLANNED",
        created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id, created_at=now, updated_at=now,
    )
    db.add(row)
    db.flush()
    _event(db, programme, ctx, "ITEM_ADDED", f"Added audit requirement: {row.title}", None,
        {"item_id": str(row.id), "title": row.title, "universe_item_id": str(row.universe_item_id), "audit_type": row.audit_type})
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _item_dict(db.query(QualityAuditProgrammeItem).options(selectinload(QualityAuditProgrammeItem.universe_item)).filter(
        QualityAuditProgrammeItem.amo_id == ctx.amo_id, QualityAuditProgrammeItem.id == row.id).one())


@router.patch("/{programme_id}/items/{item_id}")
def patch_programme_item(programme_id: str, item_id: str, payload: ProgrammeItemPatch,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme = _load_programme(db, ctx.amo_id, programme_id, for_update=True)
    _assert_editable(programme)
    row = db.query(QualityAuditProgrammeItem).filter(QualityAuditProgrammeItem.amo_id == ctx.amo_id,
        QualityAuditProgrammeItem.programme_id == programme.id, QualityAuditProgrammeItem.id == item_id).with_for_update(
            of=QualityAuditProgrammeItem
        ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Audit programme item not found.")
    before = {"title": row.title, "state": row.state, "target_start": str(row.target_start) if row.target_start else None,
              "target_end": str(row.target_end) if row.target_end else None}
    updates = payload.model_dump(exclude_unset=True, exclude={"reason"})
    # When removing a draft planned audit that still has sibling coverage for the
    # same area (e.g. two aircraft product audits), delete the row entirely so it
    # cannot linger. Sole coverage soft-cancels so hybrid rebuild does not resurrect it.
    if (
        updates.get("state") == "CANCELLED"
        and row.state == "PLANNED"
        and row.schedule_id is None
    ):
        reason = str(
            updates.get("cancellation_reason") or payload.reason or ""
        ).strip() or "Removed from the draft programme."
        sibling_count = (
            db.query(QualityAuditProgrammeItem.id)
            .filter(
                QualityAuditProgrammeItem.amo_id == ctx.amo_id,
                QualityAuditProgrammeItem.programme_id == programme.id,
                QualityAuditProgrammeItem.universe_item_id == row.universe_item_id,
                QualityAuditProgrammeItem.id != row.id,
                QualityAuditProgrammeItem.state != "CANCELLED",
            )
            .count()
        )
        if sibling_count > 0:
            title = row.title
            db.delete(row)
            _event(
                db,
                programme,
                ctx,
                "ITEM_UPDATED",
                reason,
                before,
                {"deleted": True, "title": title, "state": "DELETED"},
            )
            db.commit()
            return {
                "id": str(item_id),
                "programme_id": str(programme.id),
                "title": title,
                "state": "CANCELLED",
                "deleted": True,
            }
    updates.pop("audit_type", None)
    if row.universe_item is not None:
        updates["audit_type"] = _audit_type_for_entity(row.universe_item.entity_type)
    supporting_auditors = _normalise_supporting_auditors(
        updates.get("supporting_auditor_user_ids", list(row.supporting_auditor_user_ids or [])),
        lead_auditor_user_id=updates.get("lead_auditor_user_id", row.lead_auditor_user_id),
        observer_auditor_user_id=updates.get(
            "observer_auditor_user_id", row.observer_auditor_user_id
        ),
    )
    updates["supporting_auditor_user_ids"] = supporting_auditors
    required_schedule_fields = {
        "non_working_day_policy", "default_start_time", "default_end_time", "default_duration_days"
    }
    if any(field in updates and updates[field] is None for field in required_schedule_fields):
        raise HTTPException(status_code=422, detail="Audit timing and non-working-day settings cannot be cleared.")
    if "fixed_dates" in updates:
        updates["fixed_dates"] = _normalise_fixed_dates(updates["fixed_dates"])
    candidate_state = updates.get("state", row.state)
    if "state" in updates and candidate_state not in {"PLANNED", "CANCELLED"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scheduling, completion, follow-up and deferral states are owned by their governed workflows.",
        )
    if "deferral_reason" in updates:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Use the governed audit-deferral request, decision and apply workflow.",
        )
    if candidate_state == "CANCELLED" and not str(
        updates.get("cancellation_reason", row.cancellation_reason) or payload.reason or ""
    ).strip():
        raise HTTPException(status_code=422, detail="Cancelling an audit requirement requires a reason.")
    if "state" in updates and candidate_state == "PLANNED":
        updates["cancellation_reason"] = None
    candidate_lead_auditor = updates.get(
        "lead_auditor_user_id", row.lead_auditor_user_id
    )
    candidate_observer = updates.get(
        "observer_auditor_user_id", row.observer_auditor_user_id
    )
    if candidate_lead_auditor and candidate_observer == candidate_lead_auditor:
        raise HTTPException(
            status_code=422,
            detail="The lead auditor cannot also be the observer.",
        )
    if "mandatory_surveillance" in updates and row.universe_item and row.universe_item.mandatory_surveillance:
        updates["mandatory_surveillance"] = True
    candidate = {
        "recurrence": updates.get("recurrence", row.recurrence),
        "fixed_dates": updates.get("fixed_dates", list(row.fixed_dates or [])),
        "default_start_time": updates.get("default_start_time", row.default_start_time),
        "default_end_time": updates.get("default_end_time", row.default_end_time),
        "default_duration_days": updates.get("default_duration_days", row.default_duration_days),
        "auto_schedule": updates.get("auto_schedule", row.auto_schedule),
    }
    cancelling = candidate_state == "CANCELLED" or (
        candidate["recurrence"] == "FIXED_DATES"
        and "fixed_dates" in updates
        and not candidate["fixed_dates"]
    )
    if cancelling:
        # Removing the last month / discarding the requirement — skip schedule revalidation.
        updates["state"] = "CANCELLED"
        updates["cancellation_reason"] = (
            str(updates.get("cancellation_reason") or payload.reason or "").strip()
            or "Removed from the programme schedule."
        )
        updates["fixed_dates"] = []
        updates["auto_schedule"] = False
        for field, value in updates.items():
            setattr(row, field, value)
        row.updated_by_user_id = ctx.user_id
        row.updated_at = _utcnow()
        _event(
            db,
            programme,
            ctx,
            "ITEM_UPDATED",
            payload.reason,
            before,
            {
                "title": row.title,
                "state": row.state,
                "target_start": str(row.target_start) if row.target_start else None,
                "target_end": str(row.target_end) if row.target_end else None,
            },
        )
        db.commit()
        set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
        return _item_dict(
            db.query(QualityAuditProgrammeItem).options(
                selectinload(QualityAuditProgrammeItem.universe_item)
            ).filter(
                QualityAuditProgrammeItem.amo_id == ctx.amo_id,
                QualityAuditProgrammeItem.id == row.id,
            ).one()
        )
    if candidate["recurrence"] == "FIXED_DATES":
        try:
            _validate_default_timing(
                candidate["default_start_time"], candidate["default_end_time"], candidate["default_duration_days"]
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _apply_fixed_date_window(programme, candidate)
        updates["fixed_dates"] = candidate["fixed_dates"]
        updates["target_start"] = candidate["target_start"]
        updates["target_end"] = candidate["target_end"]
        updates["auto_schedule"] = True
    elif updates.get("recurrence") and row.recurrence == "FIXED_DATES":
        updates["fixed_dates"] = []
        updates["auto_schedule"] = False
    candidate_recurrence = updates.get("recurrence", row.recurrence)
    candidate_start = updates.get("target_start", row.target_start)
    candidate_end = updates.get("target_end", row.target_end)
    if candidate_recurrence != "FIXED_DATES" and candidate_start and candidate_end:
        updates["default_duration_days"] = _working_day_count(candidate_start, candidate_end)
    try:
        _validate_default_timing(
            updates.get("default_start_time", row.default_start_time),
            updates.get("default_end_time", row.default_end_time),
            updates.get("default_duration_days", row.default_duration_days),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "default_location" in updates:
        _validate_item_location(
            db,
            amo_id=ctx.amo_id,
            location_code=updates["default_location"],
            required=bool(row.universe_item and row.universe_item.entity_type in {"FACILITY", "STATION"}),
        )
    _validate_item_people(
        db,
        amo_id=ctx.amo_id,
        user_ids=[
            updates.get("lead_auditor_user_id", row.lead_auditor_user_id),
            updates.get("observer_auditor_user_id", row.observer_auditor_user_id),
            updates.get("auditee_user_id", row.auditee_user_id),
            *supporting_auditors,
        ],
    )
    _validate_item_auditor_privileges(
        db,
        amo_id=ctx.amo_id,
        lead_user_id=updates.get("lead_auditor_user_id", row.lead_auditor_user_id),
        observer_user_id=updates.get("observer_auditor_user_id", row.observer_auditor_user_id),
        supporting_user_ids=supporting_auditors,
    )
    for field, value in updates.items():
        setattr(row, field, value)
    if row.target_start and row.target_end and row.target_end < row.target_start:
        raise HTTPException(status_code=422, detail="target_end must be on or after target_start")
    _validate_item_window(programme, row.target_start, row.target_end)
    if row.recurrence == "CUSTOM" and not row.custom_interval_days:
        raise HTTPException(status_code=422, detail="CUSTOM recurrence requires custom_interval_days")
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    after = {"title": row.title, "state": row.state, "target_start": str(row.target_start) if row.target_start else None,
             "target_end": str(row.target_end) if row.target_end else None}
    _event(db, programme, ctx, "ITEM_UPDATED", payload.reason, before, after)
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _item_dict(db.query(QualityAuditProgrammeItem).options(selectinload(QualityAuditProgrammeItem.universe_item)).filter(
        QualityAuditProgrammeItem.amo_id == ctx.amo_id, QualityAuditProgrammeItem.id == row.id).one())
