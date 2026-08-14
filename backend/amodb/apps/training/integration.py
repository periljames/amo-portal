"""Stable Training integration boundary for QMS and DMS.

Cross-module consumers must not independently guess whether a record is
current.  This module owns the shared lifecycle, verification, and expiry
rules used by Quality privilege checks, dashboards, and Document Control
release links.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, noload

from . import models
from . import record_lifecycle


_PASS_OUTCOMES = {"PASS", "COMPETENT", "SATISFACTORY"}
_HISTORICAL_RECORD_STATUSES = {"RENEWED", "SUPERSEDED", "INACTIVE"}


def enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def training_record_status_snapshot(row: Any, *, as_of: date | None = None) -> str:
    """Return the DMS release status for one Training record projection."""

    as_of = as_of or date.today()
    lifecycle = enum_text(row.get("record_status") if hasattr(row, "get") else getattr(row, "record_status", None)) or "ACTIVE"
    source_lifecycle = enum_text(row.get("source_status") if hasattr(row, "get") else getattr(row, "source_status", None)) or "ACTIVE"
    verification = enum_text(row.get("verification_status") if hasattr(row, "get") else getattr(row, "verification_status", None))
    valid_until = row.get("valid_until") if hasattr(row, "get") else getattr(row, "valid_until", None)

    if lifecycle in _HISTORICAL_RECORD_STATUSES or source_lifecycle in _HISTORICAL_RECORD_STATUSES:
        return "SUPERSEDED"
    if verification == "REJECTED":
        return "REJECTED"
    if verification != "VERIFIED":
        return "PENDING"
    if valid_until is not None and valid_until < as_of:
        return "EXPIRED"
    return "READY"


def training_source_status_snapshot(
    table_name: str,
    row: Any,
    *,
    fallback: str,
    as_of: date | None = None,
) -> str:
    """Translate canonical Training rows into DMS workflow semantics."""

    table = str(table_name or "").lower()
    fallback_status = enum_text(fallback)
    if table == "training_records":
        return training_record_status_snapshot(row, as_of=as_of)
    if table == "training_certificate_issues":
        return "READY" if fallback_status == "VALID" else fallback_status or "PENDING"
    if table == "training_attendance_windows":
        return "COMPLETED" if fallback_status == "CERTIFIED" else fallback_status or "PENDING"
    if table == "training_assessment_instances":
        outcome = enum_text(row.get("outcome") if hasattr(row, "get") else getattr(row, "outcome", None))
        if fallback_status == "APPROVED" and outcome in _PASS_OUTCOMES:
            return "READY"
        return fallback_status or "PENDING"
    if table == "training_authorization_cases":
        decision = enum_text(row.get("decision") if hasattr(row, "get") else getattr(row, "decision", None))
        if decision == "APPROVED" or fallback_status == "APPROVED":
            return "READY"
        return decision or fallback_status or "PENDING"
    return fallback_status or "UNVERIFIED"


def current_training_evidence(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    required_codes: Iterable[str],
    as_of: date,
) -> dict[str, Any]:
    """Return verified, active and current evidence for QMS decisions."""

    required = sorted({str(code or "").strip().upper() for code in required_codes if str(code or "").strip()})
    if not required:
        return {"required": [], "satisfied": [], "missing": [], "records": [], "passed": True}

    rows = (
        db.query(models.TrainingRecord, models.TrainingCourse)
        .join(models.TrainingCourse, models.TrainingCourse.id == models.TrainingRecord.course_id)
        .options(noload("*"))
        .filter(
            models.TrainingRecord.amo_id == amo_id,
            models.TrainingRecord.user_id == user_id,
            models.TrainingCourse.amo_id == amo_id,
            models.TrainingCourse.course_id.in_(required),
            models.TrainingRecord.verification_status == models.TrainingRecordVerificationStatus.VERIFIED,
            record_lifecycle.active_records_filter(models.TrainingRecord),
            or_(models.TrainingRecord.valid_until.is_(None), models.TrainingRecord.valid_until >= as_of),
        )
        .order_by(
            models.TrainingRecord.valid_until.desc().nullslast(),
            models.TrainingRecord.completion_date.desc().nullslast(),
            models.TrainingRecord.created_at.desc().nullslast(),
            models.TrainingRecord.id.desc(),
        )
        .limit(max(250, len(required) * 4))
        .all()
    )
    current_by_code: dict[str, tuple[Any, Any]] = {}
    for record, course in rows:
        code = str(course.course_id or "").strip().upper()
        current_by_code.setdefault(code, (record, course))

    satisfied = sorted(current_by_code)
    missing = [code for code in required if code not in current_by_code]
    records = [
        {
            "record_id": str(record.id),
            "course_id": str(course.id),
            "course_code": code,
            "completion_date": record.completion_date.isoformat(),
            "valid_until": record.valid_until.isoformat() if record.valid_until else None,
            "verification_status": enum_text(record.verification_status),
            "record_status": "READY",
            "source_route": f"/training/records/{record.id}",
        }
        for code, (record, course) in sorted(current_by_code.items())
    ]
    return {"required": required, "satisfied": satisfied, "missing": missing, "records": records, "passed": not missing}


@dataclass(frozen=True)
class TrainingRecordSummary:
    total_current: int = 0
    expired: int = 0
    expiring: int = 0
    unverified: int = 0
    oldest_expiry: date | None = None


def training_record_summary(
    db: Session,
    *,
    amo_id: str,
    as_of: date,
    due_days: int = 30,
) -> TrainingRecordSummary:
    """Aggregate latest evidence once per tenant/user/course.

    Historical renewals do not inflate QMS exposure, and unverified rows never
    improve the compliance result.
    """

    ranked = (
        db.query(
            models.TrainingRecord.id.label("record_id"),
            models.TrainingRecord.valid_until.label("valid_until"),
            models.TrainingRecord.verification_status.label("verification_status"),
            func.row_number().over(
                partition_by=(models.TrainingRecord.user_id, models.TrainingRecord.course_id),
                order_by=(
                    models.TrainingRecord.valid_until.desc().nullslast(),
                    models.TrainingRecord.completion_date.desc().nullslast(),
                    models.TrainingRecord.created_at.desc().nullslast(),
                    models.TrainingRecord.id.desc(),
                ),
            ).label("record_rank"),
        )
        .filter(
            models.TrainingRecord.amo_id == amo_id,
            record_lifecycle.active_records_filter(models.TrainingRecord),
        )
        .subquery()
    )
    latest = db.query(
        ranked.c.valid_until,
        ranked.c.verification_status,
    ).filter(ranked.c.record_rank == 1).subquery()
    verified = latest.c.verification_status == models.TrainingRecordVerificationStatus.VERIFIED
    pending = latest.c.verification_status == models.TrainingRecordVerificationStatus.PENDING
    due_on = as_of + timedelta(days=max(0, due_days))

    total_current, expired, expiring, unverified, oldest_expiry = db.query(
        func.count().label("total_current"),
        func.sum(case((and_(verified, latest.c.valid_until.is_not(None), latest.c.valid_until < as_of), 1), else_=0)).label("expired"),
        func.sum(case((and_(verified, latest.c.valid_until >= as_of, latest.c.valid_until <= due_on), 1), else_=0)).label("expiring"),
        func.sum(case((pending, 1), else_=0)).label("unverified"),
        func.min(case((and_(verified, latest.c.valid_until < as_of), latest.c.valid_until), else_=None)).label("oldest_expiry"),
    ).one()
    return TrainingRecordSummary(
        total_current=int(total_current or 0),
        expired=int(expired or 0),
        expiring=int(expiring or 0),
        unverified=int(unverified or 0),
        oldest_expiry=oldest_expiry,
    )
