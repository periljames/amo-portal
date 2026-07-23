# backend/amodb/apps/rostering/commitments.py
"""Read-only cross-module commitments projected into duty rostering.

Identity is never copied into this module.  Every commitment is derived from the
canonical tenant user and its owning module, so leave, training and Quality work
cannot silently diverge from the roster planner.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from ..quality import models as quality_models
from ..training import models as training_models
from ..workforce import models as workforce_models

UTC = timezone.utc


class RosterCommitmentRead(BaseModel):
    id: str
    user_id: str
    user_full_name: str
    user_staff_code: str
    department_id: Optional[str] = None
    kind: str
    source_module: str
    source_type: str
    source_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool = False
    blocking: bool = True
    provisional: bool = False
    status: Optional[str] = None
    location_label: Optional[str] = None
    detail: Optional[str] = None
    editable: bool = False


class RosterCommitmentResponse(BaseModel):
    from_date: date
    to_date: date
    timezone_name: str
    items: list[RosterCommitmentRead] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


def _enum_value(value) -> str:
    return str(getattr(value, "value", value))


def _zone(timezone_name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _range_bounds(from_date: date, to_date: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    if to_date < from_date:
        raise ValueError("to must be on or after from")
    if (to_date - from_date).days > 366:
        raise ValueError("Commitment ranges cannot exceed 367 days")
    starts_at = datetime.combine(from_date, time.min, tzinfo=zone).astimezone(UTC)
    ends_at = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return starts_at, ends_at


def _date_window(starts_on: date, ends_on: Optional[date], zone: ZoneInfo) -> tuple[datetime, datetime]:
    starts_at = datetime.combine(starts_on, time.min, tzinfo=zone).astimezone(UTC)
    ends_at = datetime.combine((ends_on or starts_on) + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return starts_at, ends_at


def _active_people(
    db: Session,
    *,
    amo_id: str,
    user_ids: Optional[Iterable[str]],
) -> dict[str, account_models.User]:
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )
    requested = sorted({str(value) for value in (user_ids or []) if value})
    if requested:
        query = query.filter(account_models.User.id.in_(requested))
    rows = query.order_by(account_models.User.full_name.asc(), account_models.User.staff_code.asc()).all()
    return {str(row.id): row for row in rows}


def _person_fields(user: account_models.User) -> dict:
    return {
        "user_id": str(user.id),
        "user_full_name": user.full_name,
        "user_staff_code": user.staff_code,
        "department_id": str(user.department_id) if user.department_id else None,
    }


def _availability_commitments(
    db: Session,
    *,
    amo_id: str,
    people: dict[str, account_models.User],
    starts_at: datetime,
    ends_at: datetime,
    zone: ZoneInfo,
) -> list[RosterCommitmentRead]:
    if not people:
        return []
    rows = db.query(workforce_models.EmployeeAvailabilityEvent).filter(
        workforce_models.EmployeeAvailabilityEvent.amo_id == amo_id,
        workforce_models.EmployeeAvailabilityEvent.user_id.in_(list(people)),
        workforce_models.EmployeeAvailabilityEvent.starts_at < ends_at,
        workforce_models.EmployeeAvailabilityEvent.ends_at > starts_at,
    ).order_by(
        workforce_models.EmployeeAvailabilityEvent.starts_at.asc(),
        workforce_models.EmployeeAvailabilityEvent.user_id.asc(),
        workforce_models.EmployeeAvailabilityEvent.id.asc(),
    ).all()

    items: list[RosterCommitmentRead] = []
    for row in rows:
        user = people.get(str(row.user_id))
        if not user:
            continue
        local_start = row.starts_at.astimezone(zone)
        local_end = row.ends_at.astimezone(zone)
        all_day = local_start.time() == time.min and local_end.time() == time.min
        kind = _enum_value(row.availability_type)
        label = kind.replace("_", " ").title()
        items.append(RosterCommitmentRead(
            id=f"availability:{row.id}",
            **_person_fields(user),
            kind=kind,
            source_module="WORKFORCE",
            source_type=row.source_type or "AVAILABILITY",
            source_id=str(row.source_id or row.id),
            title=row.reason or label,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            all_day=all_day,
            blocking=bool(row.blocking),
            provisional=bool(row.provisional),
            status="PROVISIONAL" if row.provisional else ("BLOCKING" if row.blocking else "INFORMATIONAL"),
            detail=label,
        ))
    return items


def _training_commitments(
    db: Session,
    *,
    amo_id: str,
    people: dict[str, account_models.User],
    from_date: date,
    to_date: date,
    zone: ZoneInfo,
) -> list[RosterCommitmentRead]:
    if not people:
        return []
    excluded_participants = [
        training_models.TrainingParticipantStatus.CANCELLED,
        training_models.TrainingParticipantStatus.NO_SHOW,
        training_models.TrainingParticipantStatus.DEFERRED,
    ]
    rows = db.query(training_models.TrainingEventParticipant).join(
        training_models.TrainingEvent,
        training_models.TrainingEventParticipant.event_id == training_models.TrainingEvent.id,
    ).options(
        selectinload(training_models.TrainingEventParticipant.event).selectinload(training_models.TrainingEvent.course),
    ).filter(
        training_models.TrainingEventParticipant.amo_id == amo_id,
        training_models.TrainingEventParticipant.user_id.in_(list(people)),
        training_models.TrainingEventParticipant.status.notin_(excluded_participants),
        training_models.TrainingEvent.status != training_models.TrainingEventStatus.CANCELLED,
        training_models.TrainingEvent.starts_on <= to_date,
        or_(training_models.TrainingEvent.ends_on.is_(None), training_models.TrainingEvent.ends_on >= from_date),
    ).order_by(
        training_models.TrainingEvent.starts_on.asc(),
        training_models.TrainingEventParticipant.user_id.asc(),
        training_models.TrainingEventParticipant.id.asc(),
    ).all()

    event_ids = sorted({str(row.event_id) for row in rows})
    windows = {
        str(row.training_event_id): row
        for row in db.query(workforce_models.TrainingEventTimeWindow).filter(
            workforce_models.TrainingEventTimeWindow.amo_id == amo_id,
            workforce_models.TrainingEventTimeWindow.training_event_id.in_(event_ids or ["__none__"]),
        ).all()
    }

    items: list[RosterCommitmentRead] = []
    for participant in rows:
        user = people.get(str(participant.user_id))
        event = participant.event
        if not user or not event:
            continue
        precise = windows.get(str(event.id))
        if precise:
            event_start, event_end, all_day = precise.starts_at, precise.ends_at, False
        else:
            event_start, event_end = _date_window(event.starts_on, event.ends_on, zone)
            all_day = True
        course = getattr(event, "course", None)
        course_code = getattr(course, "course_id", None)
        course_name = getattr(course, "course_name", None)
        detail = " · ".join(value for value in [course_code, course_name, event.provider] if value)
        items.append(RosterCommitmentRead(
            id=f"training:{event.id}:{participant.user_id}",
            **_person_fields(user),
            kind="TRAINING",
            source_module="TRAINING",
            source_type="TRAINING_EVENT",
            source_id=str(event.id),
            title=event.title,
            starts_at=event_start,
            ends_at=event_end,
            all_day=all_day,
            blocking=True,
            provisional=_enum_value(participant.status) in {"SCHEDULED", "INVITED"},
            status=_enum_value(participant.status),
            location_label=event.location,
            detail=detail or None,
        ))
    return items


def _quality_commitments(
    db: Session,
    *,
    amo_id: str,
    people: dict[str, account_models.User],
    from_date: date,
    to_date: date,
    zone: ZoneInfo,
) -> list[RosterCommitmentRead]:
    if not people:
        return []
    rows = db.query(quality_models.QMSAudit).filter(
        quality_models.QMSAudit.amo_id == amo_id,
        quality_models.QMSAudit.deleted_at.is_(None),
        quality_models.QMSAudit.status != quality_models.QMSAuditStatus.CLOSED,
        quality_models.QMSAudit.planned_start.isnot(None),
        quality_models.QMSAudit.planned_start <= to_date,
        or_(quality_models.QMSAudit.planned_end.is_(None), quality_models.QMSAudit.planned_end >= from_date),
    ).order_by(
        quality_models.QMSAudit.planned_start.asc(),
        quality_models.QMSAudit.audit_ref.asc(),
        quality_models.QMSAudit.id.asc(),
    ).all()

    items: list[RosterCommitmentRead] = []
    for audit in rows:
        roles: dict[str, list[str]] = defaultdict(list)
        for label, user_id in (
            ("Lead auditor", audit.lead_auditor_user_id),
            ("Observer", audit.observer_auditor_user_id),
            ("Assistant auditor", audit.assistant_auditor_user_id),
            ("Auditee", audit.auditee_user_id),
        ):
            if user_id and str(user_id) in people:
                roles[str(user_id)].append(label)
        audit_start = audit.actual_start or audit.planned_start
        audit_end = audit.actual_end or audit.planned_end or audit_start
        if not audit_start:
            continue
        starts_at, ends_at = _date_window(audit_start, audit_end, zone)
        for user_id, labels in roles.items():
            user = people[user_id]
            items.append(RosterCommitmentRead(
                id=f"quality-audit:{audit.id}:{user_id}",
                **_person_fields(user),
                kind="QMS_AUDIT",
                source_module="QUALITY",
                source_type="QMS_AUDIT",
                source_id=str(audit.id),
                title=f"{audit.audit_ref} · {audit.title}",
                starts_at=starts_at,
                ends_at=ends_at,
                all_day=True,
                blocking=True,
                provisional=_enum_value(audit.status) == "PLANNED",
                status=_enum_value(audit.status),
                detail=", ".join(labels),
            ))
    return items


def list_commitments(
    db: Session,
    *,
    amo_id: str,
    from_date: date,
    to_date: date,
    user_ids: Optional[Iterable[str]] = None,
) -> RosterCommitmentResponse:
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
    timezone_name = getattr(amo, "time_zone", None) or "UTC"
    zone = _zone(timezone_name)
    starts_at, ends_at = _range_bounds(from_date, to_date, zone)
    people = _active_people(db, amo_id=amo_id, user_ids=user_ids)

    items = [
        *_availability_commitments(
            db,
            amo_id=amo_id,
            people=people,
            starts_at=starts_at,
            ends_at=ends_at,
            zone=zone,
        ),
        *_training_commitments(
            db,
            amo_id=amo_id,
            people=people,
            from_date=from_date,
            to_date=to_date,
            zone=zone,
        ),
        *_quality_commitments(
            db,
            amo_id=amo_id,
            people=people,
            from_date=from_date,
            to_date=to_date,
            zone=zone,
        ),
    ]
    items.sort(key=lambda row: (row.starts_at, row.user_full_name.lower(), row.kind, row.id))
    counts = Counter(row.kind for row in items)
    return RosterCommitmentResponse(
        from_date=from_date,
        to_date=to_date,
        timezone_name=timezone_name,
        items=items,
        counts=dict(sorted(counts.items())),
    )
