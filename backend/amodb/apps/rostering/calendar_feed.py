# backend/amodb/apps/rostering/calendar_feed.py
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from . import commitments, models

UTC = timezone.utc
TOKEN_PURPOSE = "rostering-personal-calendar-v1"


def _secret() -> bytes:
    value = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET_KEY")
    if not value:
        raise RuntimeError("SECRET_KEY is required for personal calendar subscriptions")
    return value.encode("utf-8")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def calendar_token(*, amo_id: str, user_id: str) -> str:
    payload = _encode(f"{amo_id}:{user_id}".encode("utf-8"))
    signature = hmac.new(_secret(), f"{TOKEN_PURPOSE}:{payload}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def decode_calendar_token(token: str) -> tuple[str, str]:
    try:
        payload, signature = token.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid calendar subscription token") from exc
    expected = hmac.new(_secret(), f"{TOKEN_PURPOSE}:{payload}".encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid calendar subscription token")
    try:
        amo_id, user_id = _decode(payload).decode("utf-8").split(":", 1)
    except Exception as exc:
        raise ValueError("Invalid calendar subscription token") from exc
    if not amo_id or not user_id:
        raise ValueError("Invalid calendar subscription token")
    return amo_id, user_id


def _escape(value: Any) -> str:
    text = str(value or "")
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _datetime(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _date(value: datetime) -> str:
    return value.date().strftime("%Y%m%d")


def _event(
    *,
    uid: str,
    starts_at: datetime,
    ends_at: datetime,
    summary: str,
    description: str = "",
    location: str = "",
    all_day: bool = False,
    status: str = "CONFIRMED",
    url: Optional[str] = None,
) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:{_escape(uid)}@amo-portal", f"DTSTAMP:{_datetime(datetime.now(UTC))}"]
    if all_day:
        lines.extend([
            f"DTSTART;VALUE=DATE:{_date(starts_at)}",
            f"DTEND;VALUE=DATE:{_date(ends_at)}",
        ])
    else:
        lines.extend([f"DTSTART:{_datetime(starts_at)}", f"DTEND:{_datetime(ends_at)}"])
    lines.extend([
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        f"LOCATION:{_escape(location)}",
        f"STATUS:{status}",
    ])
    if url:
        lines.append(f"URL:{_escape(url)}")
    lines.append("END:VEVENT")
    return lines


def _task_detail(assignment: models.RosterAssignment) -> tuple[str, str]:
    summaries: list[str] = []
    aircraft: list[str] = []
    for link in assignment.task_links or []:
        task_assignment = getattr(link, "task_assignment", None)
        task = getattr(task_assignment, "task", None)
        work_order = getattr(task, "work_order", None)
        aircraft_row = getattr(work_order, "aircraft", None)
        task_label = " · ".join(
            value for value in [
                getattr(work_order, "wo_number", None),
                getattr(task, "task_code", None),
                getattr(task, "title", None),
            ] if value
        )
        if task_label:
            summaries.append(task_label)
        aircraft_label = getattr(aircraft_row, "registration", None) or getattr(work_order, "aircraft_serial_number", None)
        if aircraft_label:
            aircraft.append(str(aircraft_label))
    return "\n".join(dict.fromkeys(summaries)), ", ".join(dict.fromkeys(aircraft))


def _published_assignments(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    from_date: date,
    to_date: date,
) -> list[models.RosterAssignment]:
    range_start = datetime.combine(from_date, datetime.min.time(), tzinfo=UTC)
    range_end = datetime.combine(to_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    return db.query(models.RosterAssignment).join(
        models.RosterVersion,
        models.RosterAssignment.version_id == models.RosterVersion.id,
    ).options(
        selectinload(models.RosterAssignment.shift_template),
        selectinload(models.RosterAssignment.base_station),
        selectinload(models.RosterAssignment.task_links)
        .selectinload(models.RosterTaskAssignmentLink.task_assignment)
        .selectinload("task")
        .selectinload("work_order")
        .selectinload("aircraft"),
    ).filter(
        models.RosterAssignment.amo_id == amo_id,
        models.RosterAssignment.user_id == user_id,
        models.RosterAssignment.deleted_at.is_(None),
        models.RosterAssignment.starts_at < range_end,
        models.RosterAssignment.ends_at > range_start,
        models.RosterVersion.status == models.RosterVersionStatus.PUBLISHED,
    ).order_by(models.RosterAssignment.starts_at.asc(), models.RosterAssignment.id.asc()).all()


def personal_calendar(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> str:
    user = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not user:
        raise ValueError("Calendar owner is not an active tenant user")
    start = from_date or (date.today() - timedelta(days=30))
    end = to_date or (date.today() + timedelta(days=400))
    if end < start or (end - start).days > 730:
        raise ValueError("Calendar range must be between 1 and 731 days")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AMO Portal//Unified Personal Operations Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape('AMO Portal · ' + user.full_name)}",
        "X-WR-CALDESC:Published duty, training, Quality audits and linked maintenance work",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]

    for assignment in _published_assignments(
        db,
        amo_id=amo_id,
        user_id=user_id,
        from_date=start,
        to_date=end,
    ):
        tasks, aircraft = _task_detail(assignment)
        shift = getattr(assignment.shift_template, "code", None) or assignment.status.value
        base = getattr(assignment.base_station, "code", None) or assignment.location_label or "Base unassigned"
        summary_parts = [shift, base]
        if aircraft:
            summary_parts.append(aircraft)
        description = "\n".join(filter(None, [
            f"Roster status: {assignment.status.value}",
            f"Role: {assignment.role_label}" if assignment.role_label else None,
            f"Team: {assignment.team_code}" if assignment.team_code else None,
            f"Aircraft: {aircraft}" if aircraft else None,
            tasks,
            assignment.task_note,
        ]))
        lines.extend(_event(
            uid=f"roster:{assignment.id}",
            starts_at=assignment.starts_at,
            ends_at=assignment.ends_at,
            summary=" · ".join(summary_parts),
            description=description,
            location=assignment.location_label or base,
        ))

    projected = commitments.list_commitments(
        db,
        amo_id=amo_id,
        from_date=start,
        to_date=end,
        user_ids=[user_id],
    )
    for item in projected.items:
        if item.source_module == "WORKFORCE" and not item.blocking:
            continue
        source_label = {
            "QUALITY": "Audit",
            "TRAINING": "Training",
            "WORKFORCE": "Availability",
        }.get(item.source_module, item.source_module.title())
        lines.extend(_event(
            uid=item.id,
            starts_at=item.starts_at,
            ends_at=item.ends_at,
            summary=f"{source_label} · {item.title}",
            description="\n".join(filter(None, [
                f"Source: {item.source_module}",
                f"Type: {item.kind.replace('_', ' ')}",
                f"Status: {item.status}" if item.status else None,
                item.detail,
            ])),
            location=item.location_label or "",
            all_day=item.all_day,
            status="TENTATIVE" if item.provisional else "CONFIRMED",
        ))

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
